from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import cast, get_args

from src.application.rag_eval.ports import RagEvalJsonLlmPort
from src.application.rag_eval.schemas import (
    RagEvalChunk,
    RagEvalDataset,
    RagEvalQuestion,
    RagEvalQuestionType,
    RagEvalSeverity,
    new_eval_id,
)

ALLOWED_QUESTION_TYPES = set(get_args(RagEvalQuestionType))
ALLOWED_SEVERITIES = set(get_args(RagEvalSeverity))

RagEvalDatasetProgressCallback = Callable[[int, int, int], Awaitable[None]]
RagEvalDatasetControlCallback = Callable[[], Awaitable[None]]

MAX_CHUNKS_PER_LLM_BATCH = 3
MAX_CHUNK_CHARS = 900


class LlmRagEvalDatasetGenerator:
    """Generates a universal RAG eval dataset from document chunks.

    No document-topic keyword dictionaries here.
    The LLM receives chunks and decides what is important in this document.
    Application code only validates question taxonomy and JSON shape.
    """

    def __init__(
        self,
        *,
        llm: RagEvalJsonLlmPort,
        model_name: str = "llm_json_provider",
    ) -> None:
        self._llm = llm
        self._model_name = model_name

    async def generate_dataset(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalChunk],
        max_questions: int,
        progress_callback: RagEvalDatasetProgressCallback | None = None,
        control_callback: RagEvalDatasetControlCallback | None = None,
    ) -> RagEvalDataset:
        dataset_id = new_eval_id("dataset")
        dataset = RagEvalDataset(
            id=dataset_id,
            project_id=project_id,
            document_id=document_id,
            status="generating",
            model_used=self._model_name,
        )

        if not chunks:
            dataset.status = "ready"
            dataset.total_questions = 0
            dataset.metadata = {"warning": "document_has_no_chunks"}
            if progress_callback is not None:
                await progress_callback(0, 0, 0)
            return dataset

        questions: list[RagEvalQuestion] = []
        target = max(max_questions, 1)
        last_batch_index = 0

        if progress_callback is not None:
            await progress_callback(0, target, 0)

        for batch_index, batch in enumerate(self._batches(chunks), start=1):
            last_batch_index = batch_index

            if len(questions) >= target:
                break

            if control_callback is not None:
                await control_callback()

            response = await self._llm.complete_json(
                system_prompt=self._system_prompt(),
                user_prompt=self._user_prompt(
                    project_id=project_id,
                    document_id=document_id,
                    chunks=batch,
                    remaining=max(target - len(questions), 1),
                    batch_index=batch_index,
                ),
                schema_name="rag_eval_questions_v1",
            )

            raw_questions = response.get("questions")
            if not isinstance(raw_questions, Sequence) or isinstance(
                raw_questions, str
            ):
                if progress_callback is not None:
                    await progress_callback(
                        min(len(self._dedupe(questions)), target),
                        target,
                        batch_index,
                    )
                continue

            for item in raw_questions:
                if not isinstance(item, Mapping):
                    continue

                question = self._question_from_payload(
                    dataset_id=dataset_id,
                    project_id=project_id,
                    document_id=document_id,
                    payload=item,
                )
                if question is not None:
                    questions.append(question)

                if len(questions) >= target:
                    break

            if progress_callback is not None:
                await progress_callback(
                    min(len(self._dedupe(questions)), target),
                    target,
                    batch_index,
                )

        dataset.questions = self._dedupe(questions)[:target]
        dataset.total_questions = len(dataset.questions)
        dataset.status = "ready"
        dataset.metadata = {
            "generation_strategy": "llm_full_chunk_coverage_batches",
            "max_questions": target,
            "source_chunk_count": len(chunks),
        }

        if progress_callback is not None:
            await progress_callback(dataset.total_questions, target, last_batch_index)

        return dataset

    def _system_prompt(self) -> str:
        question_types = ", ".join(sorted(ALLOWED_QUESTION_TYPES))
        return f"""
You generate an automatic RAG evaluation dataset for an uploaded knowledge document.

You must infer what matters from the chunks. Do not rely on a fixed business topic list.

Generate questions that test:
1. direct answerability from evidence;
2. paraphrases;
3. short vague user queries;
4. similar-but-wrong questions that must not use nearby evidence incorrectly;
5. unknown questions where the bot should say there is no information;
6. risky questions where escalation/no-answer may be required;
7. contradiction checks only if the chunks imply conflict.

Allowed question_type values:
{question_types}

Return strict JSON only. Do not include hidden chain-of-thought.
Use short observable notes in metadata, not reasoning traces.
""".strip()

    def _user_prompt(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalChunk],
        remaining: int,
        batch_index: int,
    ) -> str:
        chunk_payload = [
            {
                "chunk_id": chunk.id,
                "source": chunk.source,
                "content": self._clip(chunk.content),
                "metadata": {
                    str(key): value
                    for key, value in chunk.metadata.items()
                    if key
                    in {
                        "entry_type",
                        "title",
                        "source_excerpt",
                        "questions",
                        "synonyms",
                        "tags",
                    }
                },
            }
            for chunk in chunks
        ]

        per_batch_target = min(max(remaining, len(chunks)), 12)

        return f"""
Project id: {project_id}
Document id: {document_id}
Batch index: {batch_index}
Generate up to {per_batch_target} eval questions for these chunks.
You must cover every chunk in this batch with at least one answerable direct/paraphrase/short_vague question before adding optional negative/risky cases.
Full-document mode depends on this: every chunk should be represented in the generated dataset whenever possible.

Strict JSON shape:
{{
  "questions": [
    {{
      "question": "client question",
      "question_type": "direct | paraphrase | short_vague | similar_wrong | unknown | risky | contradiction",
      "expected_chunk_ids": ["chunk id"],
      "expected_answer_summary": "short summary of what the bot should answer, or no-answer behavior",
      "should_answer": true,
      "should_escalate": false,
      "difficulty": 1,
      "severity": "low | medium | high | critical",
      "metadata": {{
        "why": "short observable test purpose",
        "source_chunk_ids": ["chunk id"]
      }}
    }}
  ]
}}

Rules:
- For direct/paraphrase/short_vague: expected_chunk_ids should contain supporting chunk ids.
- For unknown/similar_wrong: expected_chunk_ids can be empty if the document does not support an answer.
- Do not invent chunk ids.
- Do not expect exact wording.
- Expected evidence is chunk ids, not full answer text.
- Include negative cases when adjacent unsupported questions are plausible.
- Include risky/escalation cases only when useful for this document.
- Do not include chain-of-thought.

Chunks:
{chunk_payload}
""".strip()

    def _question_from_payload(
        self,
        *,
        dataset_id: str,
        project_id: str,
        document_id: str,
        payload: Mapping[str, object],
    ) -> RagEvalQuestion | None:
        question = str(payload.get("question") or "").strip()
        question_type = str(payload.get("question_type") or "").strip()
        severity = str(payload.get("severity") or "medium").strip()

        if not question:
            return None

        if question_type not in ALLOWED_QUESTION_TYPES:
            return None

        if severity not in ALLOWED_SEVERITIES:
            severity = "medium"

        return RagEvalQuestion(
            id=new_eval_id("question"),
            dataset_id=dataset_id,
            project_id=project_id,
            document_id=document_id,
            question=question[:1000],
            question_type=cast(RagEvalQuestionType, question_type),
            expected_chunk_ids=self._string_list(payload.get("expected_chunk_ids")),
            expected_answer_summary=str(
                payload.get("expected_answer_summary") or ""
            ).strip()[:1200],
            should_answer=bool(payload.get("should_answer")),
            should_escalate=bool(payload.get("should_escalate")),
            difficulty=self._difficulty(payload.get("difficulty")),
            severity=cast(RagEvalSeverity, severity),
            metadata=self._metadata(payload.get("metadata")),
        )

    def _metadata(self, value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            return {}

        safe: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if isinstance(item, str | int | float | bool) or item is None:
                safe[key] = item
            elif isinstance(item, list):
                safe[key] = [str(part)[:300] for part in item[:20]]

        return safe

    def _string_list(self, value: object) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return []

        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text[:300])

        return result[:50]

    def _difficulty(self, value: object) -> int:
        if isinstance(value, bool):
            return 3
        if not isinstance(value, int | str):
            return 3

        try:
            parsed = int(value)
        except ValueError:
            return 3

        return max(1, min(5, parsed))

    def _dedupe(self, questions: list[RagEvalQuestion]) -> list[RagEvalQuestion]:
        seen: set[tuple[str, str]] = set()
        result: list[RagEvalQuestion] = []

        for question in questions:
            key = (question.question_type, question.question.lower().strip())
            if key in seen:
                continue
            seen.add(key)
            result.append(question)

        return result

    def _batches(self, chunks: list[RagEvalChunk]) -> list[list[RagEvalChunk]]:
        return [
            chunks[index : index + MAX_CHUNKS_PER_LLM_BATCH]
            for index in range(0, len(chunks), MAX_CHUNKS_PER_LLM_BATCH)
        ]

    def _clip(self, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) <= MAX_CHUNK_CHARS:
            return cleaned
        return cleaned[:MAX_CHUNK_CHARS].rstrip() + "…"
