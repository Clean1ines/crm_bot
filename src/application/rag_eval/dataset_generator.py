from __future__ import annotations

import json
import re
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

MAX_CHUNKS_PER_LLM_BATCH = 1
MAX_CHUNK_CHARS = 6000
MIN_VARIANTS_PER_FACT = 5


class LlmRagEvalDatasetGenerator:
    """Generates a universal fact/variant RAG eval dataset from document chunks.

    The LLM must:
    1. extract atomic facts from each chunk;
    2. generate multiple user-question variants for every extracted fact;
    3. return strict JSON only.

    Application code validates taxonomy, chunk ids and JSON shape.
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

        batches = self._batches(chunks)
        total_batches = len(batches)

        if not batches:
            dataset.status = "ready"
            dataset.total_questions = 0
            dataset.metadata = {"warning": "document_has_no_useful_chunks"}
            if progress_callback is not None:
                await progress_callback(0, 0, 0)
            return dataset

        questions: list[RagEvalQuestion] = []
        valid_chunk_ids = {chunk.id for chunk in chunks if chunk.id}

        if progress_callback is not None:
            await progress_callback(0, total_batches, 0)

        last_batch_index = 0

        for batch_index, batch in enumerate(batches, start=1):
            last_batch_index = batch_index

            if control_callback is not None:
                await control_callback()

            if progress_callback is not None:
                await progress_callback(
                    len(self._dedupe(questions)),
                    max(len(self._dedupe(questions)), total_batches),
                    batch_index - 1,
                )

            response = await self._llm.complete_json(
                system_prompt=self._system_prompt(),
                user_prompt=self._user_prompt(
                    project_id=project_id,
                    document_id=document_id,
                    chunks=batch,
                    batch_index=batch_index,
                    total_batches=total_batches,
                ),
                schema_name="rag_eval_questions_v2",
            )

            raw_questions = response.get("questions")
            if not isinstance(raw_questions, Sequence) or isinstance(
                raw_questions, str
            ):
                if progress_callback is not None:
                    await progress_callback(
                        len(self._dedupe(questions)),
                        max(len(self._dedupe(questions)), total_batches),
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
                    valid_chunk_ids=valid_chunk_ids,
                )
                if question is None:
                    continue

                questions.append(question)

            if progress_callback is not None:
                await progress_callback(
                    len(self._dedupe(questions)),
                    max(len(self._dedupe(questions)), total_batches),
                    batch_index,
                )

        dataset.questions = self._dedupe(questions)
        dataset.total_questions = len(dataset.questions)
        dataset.status = "ready"
        dataset.metadata = {
            "generation_strategy": "llm_fact_variant_coverage_batches",
            "source_chunk_count": len(chunks),
            "useful_chunk_count": sum(len(batch) for batch in batches),
            "llm_batches": total_batches,
            "min_variants_per_fact": MIN_VARIANTS_PER_FACT,
        }

        if progress_callback is not None:
            await progress_callback(
                dataset.total_questions, total_batches, last_batch_index
            )

        return dataset

    def _system_prompt(self) -> str:
        question_types = ", ".join(sorted(ALLOWED_QUESTION_TYPES))
        example = {
            "questions": [
                {
                    "question": "будет ли бот доступен клиентам круглосуточно?",
                    "question_type": "paraphrase",
                    "expected_chunk_ids": ["chunk_id_from_input"],
                    "expected_answer_summary": "Ассистент может отвечать в любое время суток, если проект и инфраструктура работают.",
                    "should_answer": True,
                    "should_escalate": False,
                    "difficulty": 2,
                    "severity": "medium",
                    "metadata": {
                        "source_chunk_ids": ["chunk_id_from_input"],
                        "fact_id": "availability_24_7_if_project_and_infrastructure_work",
                        "fact_summary": "Ассистент может отвечать в любое время суток при работающих проекте и инфраструктуре.",
                        "variant_style": "semantic_paraphrase",
                        "why": "Checks whether retrieval finds the availability fact from a natural client paraphrase.",
                    },
                }
            ]
        }
        example_json = json.dumps(example, ensure_ascii=False, indent=2)

        return f"""
You generate an automatic RAG evaluation dataset for uploaded knowledge chunks.

Your entire response MUST be one valid JSON object.
Return JSON only.
Do not return markdown.
Do not return prose.
Do not wrap JSON in code fences.
Do not include comments.
Do not include chain-of-thought or hidden reasoning.

Universal task:
1. Read each provided chunk.
2. Extract every atomic answerable fact from the chunk.
3. For every extracted fact, generate at least {MIN_VARIANTS_PER_FACT} semantically different user questions whenever possible.
4. Each question must test whether production RAG can retrieve the correct chunk and answer the correct fact.
5. Questions and expected_answer_summary must use the same language as the source chunk. Infer the language from the chunk itself. Do not translate the source material.

Variant styles to create for each fact:
- direct: close to the source heading or wording;
- semantic_paraphrase: same meaning with different words;
- short_vague: short, incomplete, natural user query;
- situational: realistic client scenario that implies the same fact;
- typo_noisy: typo, informal wording, wrong capitalization, missing punctuation;
- boundary_negative: only when useful, a similar-but-wrong or overclaiming question that should not be answered as if supported.

Allowed question_type values:
{question_types}

Map variant styles to question_type like this:
- direct -> direct
- semantic_paraphrase -> paraphrase
- situational -> paraphrase
- typo_noisy -> paraphrase or short_vague
- short_vague -> short_vague
- boundary_negative -> similar_wrong or unknown
- contradiction -> contradiction only when the chunks imply a real conflict
- risky -> risky only when the document fact requires escalation/no-answer caution

Required JSON shape example.
This example demonstrates output shape only. Do not copy its topic unless the input chunk contains that fact.

{example_json}
""".strip()

    def _user_prompt(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalChunk],
        batch_index: int,
        total_batches: int,
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

        chunks_json = json.dumps(chunk_payload, ensure_ascii=False, indent=2)

        return f"""
Project id: {project_id}
Document id: {document_id}
Batch: {batch_index}/{total_batches}

Generate a fact-variant RAG eval dataset for the chunks below.

Strict rules:
- Return only JSON with top-level key "questions".
- Do not include any key other than "questions" at the top level.
- Generate questions only from facts actually present in the chunk.
- Do not invent facts.
- Do not invent chunk ids.
- expected_chunk_ids must contain only chunk ids from the input.
- For answerable questions, expected_chunk_ids must not be empty.
- expected_answer_summary must describe the required meaning, not exact wording.
- Each question must include metadata.fact_id.
- Each question must include metadata.fact_summary.
- Each question must include metadata.variant_style.
- Each question must include metadata.source_chunk_ids.
- fact_id must be stable, short, lowercase snake_case, and derived from the fact meaning.
- Different variants of the same fact must reuse the same fact_id.
- Do not generate duplicate questions.
- Do not add explanations outside JSON.

For every extracted fact, generate at least {MIN_VARIANTS_PER_FACT} variants when possible:
1. direct
2. semantic_paraphrase
3. short_vague
4. situational
5. typo_noisy

Add boundary_negative / similar_wrong / unknown variants only when they are natural and useful for this chunk.

Chunks JSON:
{chunks_json}
""".strip()

    def _question_from_payload(
        self,
        *,
        dataset_id: str,
        project_id: str,
        document_id: str,
        payload: Mapping[str, object],
        valid_chunk_ids: set[str],
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

        expected_chunk_ids = [
            chunk_id
            for chunk_id in self._string_list(payload.get("expected_chunk_ids"))
            if chunk_id in valid_chunk_ids
        ]

        raw_should_answer = payload.get("should_answer")
        should_answer = (
            raw_should_answer
            if isinstance(raw_should_answer, bool)
            else bool(expected_chunk_ids)
        )

        if should_answer and not expected_chunk_ids:
            return None

        metadata = self._metadata(payload.get("metadata"))
        source_chunk_ids = [
            chunk_id
            for chunk_id in self._string_list(metadata.get("source_chunk_ids"))
            if chunk_id in valid_chunk_ids
        ]
        if not source_chunk_ids and expected_chunk_ids:
            source_chunk_ids = list(expected_chunk_ids)

        if source_chunk_ids:
            metadata["source_chunk_ids"] = source_chunk_ids

        if not str(metadata.get("fact_id") or "").strip():
            metadata["fact_id"] = self._fallback_fact_id(
                str(payload.get("expected_answer_summary") or question)
            )

        if not str(metadata.get("fact_summary") or "").strip():
            metadata["fact_summary"] = str(
                payload.get("expected_answer_summary") or ""
            ).strip()[:500]

        if not str(metadata.get("variant_style") or "").strip():
            metadata["variant_style"] = question_type

        return RagEvalQuestion(
            id=new_eval_id("question"),
            dataset_id=dataset_id,
            project_id=project_id,
            document_id=document_id,
            question=question[:1000],
            question_type=cast(RagEvalQuestionType, question_type),
            expected_chunk_ids=expected_chunk_ids,
            expected_answer_summary=str(
                payload.get("expected_answer_summary") or ""
            ).strip()[:1200],
            should_answer=bool(should_answer),
            should_escalate=bool(payload.get("should_escalate")),
            difficulty=self._difficulty(payload.get("difficulty")),
            severity=cast(RagEvalSeverity, severity),
            metadata=metadata,
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
        seen: set[str] = set()
        result: list[RagEvalQuestion] = []

        for question in questions:
            key = self._normalized_question(question.question)
            if key in seen:
                continue
            seen.add(key)
            result.append(question)

        return result

    def _normalized_question(self, value: str) -> str:
        return " ".join(value.lower().strip().split())

    def _fallback_fact_id(self, value: str) -> str:
        normalized = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "_", value.lower())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return (normalized or "fact")[:80]

    def _is_useful_chunk(self, chunk: RagEvalChunk) -> bool:
        content = " ".join(chunk.content.split())
        if not content:
            return False
        if content in {"---", "***", "___", "--", "-"}:
            return False
        if re.fullmatch(r"[-*_]{3,}", content):
            return False
        if content[0] in {",", ";", ":", ".", ")", "]"}:
            return False

        return True

    def _batches(self, chunks: list[RagEvalChunk]) -> list[list[RagEvalChunk]]:
        useful_chunks = [chunk for chunk in chunks if self._is_useful_chunk(chunk)]
        return [
            useful_chunks[index : index + MAX_CHUNKS_PER_LLM_BATCH]
            for index in range(0, len(useful_chunks), MAX_CHUNKS_PER_LLM_BATCH)
        ]

    def _clip(self, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) <= MAX_CHUNK_CHARS:
            return cleaned
        return cleaned[:MAX_CHUNK_CHARS].rstrip() + "…"
