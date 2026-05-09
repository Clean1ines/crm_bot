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
MAX_CHUNK_CHARS = 700
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

            response = await self._complete_questions_json(
                project_id=project_id,
                document_id=document_id,
                batch=batch,
                batch_index=batch_index,
                total_batches=total_batches,
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

    async def _complete_questions_json(
        self,
        *,
        project_id: str,
        document_id: str,
        batch: list[RagEvalChunk],
        batch_index: int,
        total_batches: int,
    ) -> Mapping[str, object]:
        try:
            return await self._llm.complete_json(
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
        except ValueError as exc:
            # Production LLMs can return truncated or malformed JSON.
            # A single bad batch must not kill the whole full-document eval.
            return {
                "questions": [
                    self._fallback_question_payload(chunk, error=exc)
                    for chunk in batch
                    if chunk.id
                ],
                "_fallback_reason": self._safe_error_text(exc),
            }

    def _fallback_question_payload(
        self,
        chunk: RagEvalChunk,
        *,
        error: ValueError,
    ) -> dict[str, object]:
        expected_answer_summary = self._fallback_expected_answer_summary(chunk)
        source_chunk_ids = [chunk.id] if chunk.id else []
        return {
            "question": self._fallback_question_text(chunk),
            "question_type": "direct",
            "expected_chunk_ids": source_chunk_ids,
            "expected_answer_summary": expected_answer_summary,
            "should_answer": bool(source_chunk_ids),
            "should_escalate": False,
            "difficulty": 2,
            "severity": "medium",
            "metadata": {
                "fact_id": self._fallback_fact_id(expected_answer_summary or chunk.id),
                "fact_summary": expected_answer_summary,
                "variant_style": "deterministic_fallback_after_invalid_llm_json",
                "source_chunk_ids": source_chunk_ids,
                "fallback_reason": self._safe_error_text(error),
            },
        }

    def _fallback_question_text(self, chunk: RagEvalChunk) -> str:
        title = str(chunk.metadata.get("title") or "").strip()
        if title:
            return f"Что сказано в разделе «{title}»?"

        preview = " ".join(chunk.content.split())[:90].rstrip(" .,:;")
        if preview:
            return f"Что говорится в фрагменте: {preview}?"

        return "Какую информацию содержит этот раздел базы знаний?"

    def _fallback_expected_answer_summary(self, chunk: RagEvalChunk) -> str:
        source_excerpt = str(chunk.metadata.get("source_excerpt") or "").strip()
        source_text = source_excerpt or chunk.content
        return self._clip(source_text)

    def _safe_error_text(self, exc: BaseException, *, max_chars: int = 500) -> str:
        text = str(exc).strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."

    def _system_prompt(self) -> str:
        question_types = ",".join(sorted(ALLOWED_QUESTION_TYPES))
        return (
            "Role: generate RAG eval questions from one KB chunk. "
            "Output: one compact valid JSON object only, top-level key questions. "
            "No markdown, prose, comments, code fences, or reasoning. "
            "Use source language. Extract every atomic answerable fact. "
            f"For each fact emit >= {MIN_VARIANTS_PER_FACT} meaning-diverse questions when possible. "
            "Variant styles: direct, paraphrase, vague, typo/slang, client_context, edge_case. "
            "Add unknown/similar_wrong/risky/contradiction only when grounded and useful. "
            f"Allowed question_type values: {question_types}. "
            "Each item needs question, question_type, expected_chunk_ids, expected_answer_summary, "
            "should_answer, should_escalate, difficulty, severity, metadata. "
            "metadata must include fact_id, fact_summary, variant_style, source_chunk_ids. "
            "Same fact variants reuse same fact_id and fact_summary."
        )

    def _user_prompt(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalChunk],
        batch_index: int,
        total_batches: int | None = None,
    ) -> str:
        chunks_json = json.dumps(
            [
                {
                    "id": chunk.id,
                    "src": chunk.source,
                    "text": self._clip(chunk.content),
                    "m": self._prompt_metadata(chunk.metadata),
                }
                for chunk in chunks
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        example_json = json.dumps(
            {
                "questions": [
                    {
                        "question": "будет ли бот отвечать ночью?",
                        "question_type": "paraphrase",
                        "expected_chunk_ids": ["chunk_id"],
                        "expected_answer_summary": "Ассистент отвечает в любое время суток, если проект и инфраструктура работают.",
                        "should_answer": True,
                        "should_escalate": False,
                        "difficulty": 2,
                        "severity": "medium",
                        "metadata": {
                            "fact_id": "assistant_24_7_if_project_and_infra_work",
                            "fact_summary": "Ассистент может отвечать в любое время суток при работающих проекте и инфраструктуре.",
                            "variant_style": "semantic_paraphrase",
                            "source_chunk_ids": ["chunk_id"],
                        },
                    }
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        batch_label = (
            f"{batch_index}/{total_batches}"
            if total_batches is not None
            else str(batch_index)
        )

        lines = [
            f"p={project_id}",
            f"d={document_id}",
            f"b={batch_label}",
            "Return JSON only. Minify.",
            f"schema_example={example_json}",
            "Rules:",
            "- Extract all atomic facts from chunks.",
            f"- For each fact emit >= {MIN_VARIANTS_PER_FACT} variants when possible.",
            "- Required variants: direct, paraphrase, vague, typo/slang, client_context, edge_case.",
            "- Same fact => same metadata.fact_id and metadata.fact_summary.",
            "- Answerable => should_answer=true and expected_chunk_ids uses only input ids.",
            "- Unsupported adjacent trap => should_answer=false and expected_chunk_ids=[].",
            "- expected_answer_summary = compact expected answer/no-answer behavior.",
            "- Do not invent ids. No reasoning.",
            f"chunks={chunks_json}",
        ]
        return chr(10).join(lines)

    def _prompt_metadata(self, metadata: Mapping[str, object]) -> dict[str, object]:
        keep = {
            "title": "t",
            "entry_type": "type",
            "source_excerpt": "ex",
            "questions": "q",
            "synonyms": "syn",
            "tags": "tags",
        }
        result: dict[str, object] = {}
        for source_key, compact_key in keep.items():
            value = metadata.get(source_key)
            compact = self._compact_prompt_value(value)
            if compact is not None:
                result[compact_key] = compact
        return result

    def _compact_prompt_value(self, value: object) -> object | None:
        if value is None:
            return None

        if isinstance(value, str):
            text = " ".join(value.split())
            if not text:
                return None
            return text[:240]

        if isinstance(value, list | tuple):
            result: list[str] = []
            for item in value[:8]:
                text = " ".join(str(item or "").split())
                if text:
                    result.append(text[:80])
            return result or None

        text = " ".join(str(value).split())
        if not text:
            return None
        return text[:160]

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
