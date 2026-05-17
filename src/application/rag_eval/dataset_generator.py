from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast, get_args

from src.application.rag_eval.ports import (
    RagEvalDatasetMetricsCallback,
    RagEvalJsonLlmPort,
)
from src.domain.project_plane.knowledge_retrieval_surface import (
    RUNTIME_ENTRY_KIND_VALUES,
)
from src.application.rag_eval.schemas import (
    RagEvalEvidenceEntry,
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


@dataclass(frozen=True, slots=True)
class _BatchGenerationResult:
    batch_index: int
    questions: list[RagEvalQuestion]
    failed: bool = False
    skipped: bool = False
    json_parse_failures: int = 0
    provider_failures: int = 0
    retry_count: int = 0
    used_fallback: bool = False


MAX_ENTRIES_PER_LLM_BATCH = 1
MAX_CHUNK_CHARS = 700
MIN_QUESTION_VARIANTS_PER_ENTRY = 8
MIN_EVAL_SOURCE_CONTENT_CHARS = 16
MIN_CONTAINED_EVAL_SOURCE_CHARS = 24

EVAL_QUESTION_SOURCE_ENTRY_KINDS = RUNTIME_ENTRY_KIND_VALUES
EXCLUDED_EVAL_SOURCE_ENTRY_KINDS: frozenset[str] = frozenset()


DOCUMENT_STRUCTURE_QUESTION_MARKERS = (
    "что сказано в разделе",
    "что написано в разделе",
    "есть ли в документе раздел",
    "раздел с номером",
    "номер раздела",
    "в каком разделе",
    "о чём речь в первой части",
    "о чем речь в первой части",
    "первая часть",
    "этот фрагмент",
    "данный фрагмент",
    "в этом фрагменте",
    "фрагмент документа",
    "заголовок раздела",
    "где указано",
    "где написано",
    "о чём речь",
    "о чем речь",
)


def is_document_structure_eval_question(question: str) -> bool:
    normalized = " ".join(question.casefold().split())

    if any(marker in normalized for marker in DOCUMENT_STRUCTURE_QUESTION_MARKERS):
        return True

    if "раздел" in normalized and (
        "что сказано" in normalized
        or "что написано" in normalized
        or "есть ли" in normalized
        or "номер" in normalized
    ):
        return True

    if normalized.startswith("где ") and (
        "указано" in normalized
        or "написано" in normalized
        or "найти информацию" in normalized
    ):
        return True

    return False


RAG_EVAL_QUESTION_QUALITY_RULES = """
Generate real client/user question variants for a single published runtime
knowledge entry, not a scientific dataset and not questions about source
document structure.

Strictly forbidden:
- decomposing the entry into separate atomic eval facts;
- rewriting or improving the answer text;
- questions about section numbers, headings, fragments, paragraphs, first part,
  "what is written in section X", "is there section X";
- questions whose answer is merely that a section exists;
- questions asking where information is located in the document;
- questions copied from built-in test sections;
- near-duplicate questions that repeat existing enrichment questions/synonyms.

Allowed useful variants:
- semantic paraphrases;
- synonymic phrasings;
- typo/misspelling variants;
- colloquial client wording;
- short/incomplete questions;
- vague but still entry-related questions.
"""


class LlmRagEvalDatasetGenerator:
    """Generates retrieval-only user question variants per canonical entry.

    The LLM receives exactly one runtime canonical entry and returns compact
    JSON with non-duplicate user question variants. Application code, not the
    LLM, attaches expected_entry_ids, expected_answer_summary and metadata.
    """

    def __init__(
        self,
        *,
        llm: RagEvalJsonLlmPort,
        model_name: str = "llm_json_provider",
        max_concurrency: int = 2,
        max_batch_attempts: int = 2,
    ) -> None:
        self._llm = llm
        self._model_name = model_name
        self._max_concurrency = max(1, min(8, max_concurrency))
        self._max_batch_attempts = max(1, min(5, max_batch_attempts))

    async def generate_dataset(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalEvidenceEntry],
        progress_callback: RagEvalDatasetProgressCallback | None = None,
        control_callback: RagEvalDatasetControlCallback | None = None,
        metrics_callback: RagEvalDatasetMetricsCallback | None = None,
    ) -> RagEvalDataset:
        dataset_id = new_eval_id("dataset")
        dataset = RagEvalDataset(
            id=dataset_id,
            project_id=project_id,
            document_id=document_id,
            status="generating",
            model_used=self._model_name,
        )

        eval_chunks = self._eval_source_chunks(chunks)
        batches = self._batches(eval_chunks)
        total_batches = len(batches)

        if not batches:
            dataset.status = "ready"
            dataset.total_questions = 0
            dataset.metadata = {"warning": "document_has_no_useful_entries"}
            if progress_callback is not None:
                await progress_callback(0, 0, 0)
            if metrics_callback is not None:
                await metrics_callback(
                    {
                        "generated_questions": 0,
                        "target_questions": 0,
                        "processed_batches": 0,
                        "total_batches": 0,
                        "successful_batches": 0,
                        "failed_batches": 0,
                        "skipped_batches": 0,
                        "json_parse_failures": 0,
                        "provider_failures": 0,
                        "retry_count": 0,
                        "dataset_generation_concurrency": self._max_concurrency,
                        "dataset_batch_attempts": self._max_batch_attempts,
                    }
                )
            return dataset

        questions: list[RagEvalQuestion] = []
        valid_entry_ids = {chunk.id for chunk in chunks if chunk.id}
        related_entry_ids_by_id = self._canonical_related_entry_ids(eval_chunks)
        completed_batches = 0
        failed_batches = 0
        skipped_batches = 0
        json_parse_failures = 0
        provider_failures = 0
        retry_count = 0
        fallback_used_count = 0

        async def emit_progress() -> None:
            deduped_count = len(self._dedupe(questions))
            target = max(deduped_count, total_batches)
            if progress_callback is not None:
                await progress_callback(deduped_count, target, completed_batches)
            if metrics_callback is not None:
                await metrics_callback(
                    {
                        "generated_questions": deduped_count,
                        "target_questions": target,
                        "processed_batches": completed_batches,
                        "total_batches": total_batches,
                        "successful_batches": completed_batches
                        - failed_batches
                        - skipped_batches,
                        "failed_batches": failed_batches,
                        "skipped_batches": skipped_batches,
                        "json_parse_failures": json_parse_failures,
                        "provider_failures": provider_failures,
                        "retry_count": retry_count,
                        "fallback_used_count": fallback_used_count,
                        "dataset_generation_concurrency": self._max_concurrency,
                        "dataset_batch_attempts": self._max_batch_attempts,
                    }
                )

        await emit_progress()

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def process_batch(
            batch_index: int,
            batch: list[RagEvalEvidenceEntry],
        ) -> _BatchGenerationResult:
            if control_callback is not None:
                await control_callback()

            async with semaphore:
                if control_callback is not None:
                    await control_callback()

                return await self._generate_batch_questions(
                    dataset_id=dataset_id,
                    project_id=project_id,
                    document_id=document_id,
                    batch=batch,
                    batch_index=batch_index,
                    total_batches=total_batches,
                    valid_entry_ids=valid_entry_ids,
                    related_entry_ids_by_id=related_entry_ids_by_id,
                    control_callback=control_callback,
                )

        tasks = [
            asyncio.create_task(process_batch(batch_index, batch))
            for batch_index, batch in enumerate(batches, start=1)
        ]

        try:
            for task in asyncio.as_completed(tasks):
                if control_callback is not None:
                    await control_callback()

                result = await task
                completed_batches += 1
                failed_batches += 1 if result.failed else 0
                skipped_batches += 1 if result.skipped else 0
                json_parse_failures += result.json_parse_failures
                provider_failures += result.provider_failures
                retry_count += result.retry_count
                fallback_used_count += 1 if result.used_fallback else 0
                questions.extend(result.questions)
                await emit_progress()
        except Exception:
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise

        dataset.questions = self._dedupe(questions)
        dataset.total_questions = len(dataset.questions)
        dataset.status = "ready"
        dataset.metadata = {
            "generation_strategy": "parallel_llm_entry_question_variant_batches",
            "source_entry_count": len(chunks),
            "canonical_eval_unit_count": len(eval_chunks),
            "useful_entry_count": sum(len(batch) for batch in batches),
            "llm_batches": total_batches,
            "min_question_variants_per_entry": MIN_QUESTION_VARIANTS_PER_ENTRY,
            "dataset_generation_concurrency": self._max_concurrency,
            "dataset_batch_attempts": self._max_batch_attempts,
            "successful_batches": completed_batches - failed_batches - skipped_batches,
            "failed_batches": failed_batches,
            "skipped_batches": skipped_batches,
            "json_parse_failures": json_parse_failures,
            "provider_failures": provider_failures,
            "retry_count": retry_count,
            "fallback_used_count": fallback_used_count,
        }

        await emit_progress()

        return dataset

    async def _generate_batch_questions(
        self,
        *,
        dataset_id: str,
        project_id: str,
        document_id: str,
        batch: list[RagEvalEvidenceEntry],
        batch_index: int,
        total_batches: int,
        valid_entry_ids: set[str],
        related_entry_ids_by_id: Mapping[str, list[str]],
        control_callback: RagEvalDatasetControlCallback | None = None,
    ) -> _BatchGenerationResult:
        json_parse_failures = 0
        provider_failures = 0
        retry_count = 0
        last_error: BaseException | None = None

        for attempt in range(1, self._max_batch_attempts + 1):
            if control_callback is not None:
                await control_callback()

            try:
                response = await self._llm.complete_json(
                    system_prompt=RAG_EVAL_QUESTION_QUALITY_RULES
                    + "\n\n"
                    + self._system_prompt(),
                    user_prompt=self._user_prompt(
                        project_id=project_id,
                        document_id=document_id,
                        chunks=batch,
                        batch_index=batch_index,
                        total_batches=total_batches,
                    ),
                    schema_name="rag_eval_questions_v2",
                )
                return self._batch_result_from_response(
                    dataset_id=dataset_id,
                    project_id=project_id,
                    document_id=document_id,
                    batch_index=batch_index,
                    response=response,
                    valid_entry_ids=valid_entry_ids,
                    related_entry_ids_by_id=related_entry_ids_by_id,
                    source_entries_by_id={
                        chunk.id: chunk for chunk in batch if chunk.id
                    },
                    json_parse_failures=json_parse_failures,
                    provider_failures=provider_failures,
                    retry_count=retry_count,
                )
            except ValueError as exc:
                last_error = exc
                if isinstance(exc, json.JSONDecodeError):
                    json_parse_failures += 1
                else:
                    provider_failures += 1
                if attempt < self._max_batch_attempts:
                    retry_count += 1
                    continue
            except Exception as exc:
                last_error = exc
                provider_failures += 1
                if attempt < self._max_batch_attempts:
                    retry_count += 1
                    continue

        fallback_error = last_error or ValueError("RAG eval question batch failed")
        fallback_payload = {
            "questions": [
                self._fallback_question_payload(chunk, error=fallback_error)
                for chunk in batch
                if chunk.id
            ],
            "_fallback_reason": self._safe_error_text(fallback_error),
        }
        fallback_result = self._batch_result_from_response(
            dataset_id=dataset_id,
            project_id=project_id,
            document_id=document_id,
            batch_index=batch_index,
            response=fallback_payload,
            valid_entry_ids=valid_entry_ids,
            related_entry_ids_by_id=related_entry_ids_by_id,
            source_entries_by_id={chunk.id: chunk for chunk in batch if chunk.id},
            json_parse_failures=json_parse_failures,
            provider_failures=provider_failures,
            retry_count=retry_count,
        )
        return _BatchGenerationResult(
            batch_index=batch_index,
            questions=fallback_result.questions,
            failed=True,
            skipped=not fallback_result.questions,
            json_parse_failures=json_parse_failures,
            provider_failures=provider_failures,
            retry_count=retry_count,
            used_fallback=True,
        )

    def _batch_result_from_response(
        self,
        *,
        dataset_id: str,
        project_id: str,
        document_id: str,
        batch_index: int,
        response: Mapping[str, object],
        valid_entry_ids: set[str],
        related_entry_ids_by_id: Mapping[str, list[str]],
        source_entries_by_id: Mapping[str, RagEvalEvidenceEntry],
        json_parse_failures: int,
        provider_failures: int,
        retry_count: int,
    ) -> _BatchGenerationResult:
        raw_questions = response.get("questions")
        if not isinstance(raw_questions, Sequence) or isinstance(raw_questions, str):
            return _BatchGenerationResult(
                batch_index=batch_index,
                questions=[],
                skipped=True,
                json_parse_failures=json_parse_failures,
                provider_failures=provider_failures,
                retry_count=retry_count,
            )

        questions: list[RagEvalQuestion] = []
        for item in raw_questions:
            if not isinstance(item, Mapping):
                continue

            question = self._question_from_payload(
                dataset_id=dataset_id,
                project_id=project_id,
                document_id=document_id,
                payload=item,
                valid_entry_ids=valid_entry_ids,
                related_entry_ids_by_id=related_entry_ids_by_id,
                source_entries_by_id=source_entries_by_id,
            )
            if question is not None and not is_document_structure_eval_question(
                question.question
            ):
                questions.append(question)

        return _BatchGenerationResult(
            batch_index=batch_index,
            questions=questions,
            skipped=not questions,
            json_parse_failures=json_parse_failures,
            provider_failures=provider_failures,
            retry_count=retry_count,
        )

    def _fallback_question_payload(
        self,
        chunk: RagEvalEvidenceEntry,
        *,
        error: BaseException,
    ) -> dict[str, object]:
        expected_answer_summary = self._fallback_expected_answer_summary(chunk)
        source_chunk_ids = self._chunk_related_ids(chunk)
        return {
            "question": self._fallback_question_text(chunk),
            "question_type": "direct",
            "expected_entry_ids": source_chunk_ids,
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

    def _fallback_question_text(self, chunk: RagEvalEvidenceEntry) -> str:
        title = str(chunk.metadata.get("title") or "").strip()
        if title:
            return f"Какой практический факт нужно знать по теме «{title}»?"

        preview = " ".join(chunk.content.split())[:90].rstrip(" .,:;")
        if preview:
            return "Какой практический вывод следует из этой информации?"

        return "Какой практический факт содержит эта база знаний?"

    def _fallback_expected_answer_summary(self, chunk: RagEvalEvidenceEntry) -> str:
        source_excerpt = str(chunk.metadata.get("source_excerpt") or "").strip()
        source_text = source_excerpt or chunk.content
        return self._clip(source_text)

    def _safe_error_text(self, exc: BaseException, *, max_chars: int = 500) -> str:
        text = str(exc).strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."

    def _system_prompt(self) -> str:
        return (
            "Role: generate non-duplicate user question variants for exactly one "
            "published/runtime canonical knowledge entry. "
            'Output compact valid JSON only: {"questions":[...]} with no markdown, '
            "prose, comments, code fences, or reasoning. "
            "Each question item must contain question, variant_style and reason. "
            "Allowed variant_style values: paraphrase, synonymic, typo, colloquial, short, vague. "
            "Generate semantic paraphrases, synonymic phrasings, typo/misspelling variants, "
            "colloquial client wording, short/incomplete questions and vague-but-still-relevant questions. "
            "Do not extract atomic facts. Do not rewrite the answer. Do not invent facts. "
            "Do not duplicate existing questions or existing synonyms from the entry enrichment. "
            "The backend will attach expected_entry_id, expected_answer_summary, should_answer and metadata."
        )

    def _user_prompt(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalEvidenceEntry],
        batch_index: int,
        total_batches: int | None = None,
    ) -> str:
        entries_json = json.dumps(
            [self._prompt_entry(chunk) for chunk in chunks],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        example_json = json.dumps(
            {
                "questions": [
                    {
                        "question": "бот ночью ответит?",
                        "variant_style": "short",
                        "reason": "Short natural client wording for the same entry.",
                    },
                    {
                        "question": "а если написать не в рабочее время, ассистент среагирует?",
                        "variant_style": "colloquial",
                        "reason": "Conversational paraphrase that should retrieve this entry.",
                    },
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
            f"project_id={project_id}",
            f"document_id={document_id}",
            f"entry_batch={batch_label}",
            "Return compact JSON only. Minify.",
            f"schema_example={example_json}",
            "Task:",
            "- Generate non-duplicate user question variants for this entry.",
            "- Use the entry answer as meaning boundary, not as text to rewrite.",
            "- Use existing_questions and existing_synonyms only to avoid duplicates.",
            "- Include paraphrase, synonymic, typo, colloquial, short and vague variants when useful.",
            "- Vague variants must still belong to this exact entry.",
            "Strictly forbidden:",
            "- Do not decompose this entry into separate fact-level eval items.",
            "- Do not extract atomic facts at all.",
            "- Do not rewrite answer.",
            "- Do not return expected_entry_ids, should_answer or expected_answer_summary.",
            "- Do not duplicate existing_questions or existing_synonyms.",
            f"entries={entries_json}",
        ]
        return chr(10).join(lines)

    def _prompt_entry(self, chunk: RagEvalEvidenceEntry) -> dict[str, object]:
        return {
            "id": chunk.id,
            "title": self._metadata_text(chunk.metadata, "title"),
            "answer": self._clip(chunk.content),
            "enrichment": {
                "questions": self._compact_prompt_value(chunk.metadata.get("questions"))
                or [],
                "synonyms": self._compact_prompt_value(chunk.metadata.get("synonyms"))
                or [],
            },
            "tags": self._compact_prompt_value(chunk.metadata.get("tags")) or [],
        }

    def _prompt_metadata(self, metadata: Mapping[str, object]) -> dict[str, object]:
        keep = {
            "title": "t",
            "entry_kind": "type",
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

    def _question_type_from_variant_style(
        self, variant_style: str
    ) -> RagEvalQuestionType:
        normalized = variant_style.strip().lower()
        if normalized in {"short", "vague"}:
            return "short_vague"
        if normalized in {"typo", "colloquial", "synonymic", "paraphrase"}:
            return "paraphrase"
        if normalized in ALLOWED_QUESTION_TYPES:
            return cast(RagEvalQuestionType, normalized)
        return "paraphrase"

    def _question_from_payload(
        self,
        *,
        dataset_id: str,
        project_id: str,
        document_id: str,
        payload: Mapping[str, object],
        valid_entry_ids: set[str],
        related_entry_ids_by_id: Mapping[str, list[str]],
        source_entries_by_id: Mapping[str, RagEvalEvidenceEntry],
    ) -> RagEvalQuestion | None:
        question = str(payload.get("question") or "").strip()
        if not question:
            return None

        source_chunk_id = ""
        if source_entries_by_id:
            source_chunk_id = next(iter(source_entries_by_id.keys()))
        source_entry = source_entries_by_id.get(source_chunk_id)
        if not source_chunk_id or source_chunk_id not in valid_entry_ids:
            return None

        metadata = self._metadata(payload.get("metadata"))
        metadata_variant_style = str(metadata.get("variant_style") or "").strip()
        variant_style = str(
            payload.get("variant_style")
            or metadata_variant_style
            or payload.get("question_type")
            or "paraphrase"
        ).strip()
        raw_question_type = str(payload.get("question_type") or "").strip()
        question_type = (
            cast(RagEvalQuestionType, raw_question_type)
            if raw_question_type in ALLOWED_QUESTION_TYPES
            else self._question_type_from_variant_style(variant_style)
        )
        expected_entry_ids = self._expand_related_entry_ids(
            [source_chunk_id],
            valid_entry_ids=valid_entry_ids,
            related_entry_ids_by_id=related_entry_ids_by_id,
        )
        if not expected_entry_ids:
            return None

        metadata["source_chunk_id"] = source_chunk_id
        metadata["expected_entry_id"] = source_chunk_id
        metadata["source_chunk_ids"] = list(expected_entry_ids)
        metadata["variant_style"] = variant_style or question_type
        reason = str(payload.get("reason") or "").strip()
        if reason:
            metadata["variant_reason"] = reason[:500]

        expected_answer_summary = ""
        if source_entry is not None:
            expected_answer_summary = self._fallback_expected_answer_summary(
                source_entry
            )
        if not expected_answer_summary:
            expected_answer_summary = str(
                payload.get("expected_answer_summary") or ""
            ).strip()
        expected_answer_summary = expected_answer_summary[:1200]

        if not str(metadata.get("fact_id") or "").strip():
            metadata["fact_id"] = self._fallback_fact_id(source_chunk_id)

        if not str(metadata.get("fact_summary") or "").strip():
            metadata["fact_summary"] = expected_answer_summary[:500]

        if self._is_low_quality_question(
            question=question,
            expected_answer_summary=expected_answer_summary,
            metadata=metadata,
        ):
            return None

        return RagEvalQuestion(
            id=new_eval_id("question"),
            dataset_id=dataset_id,
            project_id=project_id,
            document_id=document_id,
            question=question[:1000],
            question_type=question_type,
            expected_entry_ids=expected_entry_ids,
            expected_answer_summary=expected_answer_summary,
            should_answer=True,
            should_escalate=False,
            difficulty=2,
            severity="medium",
            metadata=metadata,
        )

    def _is_low_quality_question(
        self,
        *,
        question: str,
        expected_answer_summary: str,
        metadata: Mapping[str, object],
    ) -> bool:
        """Reject eval items that test document scaffolding instead of KB facts."""

        normalized_question = self._normalized_for_quality(question)
        normalized_summary = self._normalized_for_quality(expected_answer_summary)
        normalized_fact_summary = self._normalized_for_quality(
            str(metadata.get("fact_summary") or "")
        )

        combined_summary = f"{normalized_summary} {normalized_fact_summary}".strip()

        if not normalized_question:
            return True

        meta_summary_markers = (
            "document contains a section",
            "section titled",
            "contains section titled",
            "документ содержит раздел",
            "раздел с названием",
            "section ",
        )
        if any(marker in combined_summary for marker in meta_summary_markers):
            return True

        structure_question_patterns = (
            r"\bесть\s+ли\s+в\s+документе\s+(раздел|пункт|секция)",
            r"\bесть\s+ли\s+.*\bраздел\s+с\s+номером\b",
            r"\bчто\s+(сказано|написано|говорится)\s+в\s+(разделе|пункте|фрагменте)\b",
            r"\bкакую\s+информацию\s+содержит\s+.*\bраздел\s+базы\s+знаний\b",
            r"\bраздел\s+номер\s+\d+\b",
            r"\bsection\s+(number\s+)?\d+\b",
            r"\bdoes\s+the\s+document\s+contain\s+a\s+section\b",
            r"\bwhat\s+is\s+written\s+in\s+section\b",
        )
        if any(
            re.search(pattern, normalized_question)
            for pattern in structure_question_patterns
        ):
            return True

        if (
            "документ" in normalized_question
            and "раздел" in normalized_question
            and any(
                token in normalized_question
                for token in ("номер", "назван", "называет")
            )
        ):
            return True

        return False

    def _normalized_for_quality(self, value: str) -> str:
        normalized = " ".join(value.lower().strip().split())
        normalized = normalized.replace("ё", "е")
        return normalized

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

    def _chunk_related_ids(self, chunk: RagEvalEvidenceEntry) -> list[str]:
        related_ids = self._string_list(chunk.metadata.get("related_entry_ids"))
        if chunk.id and chunk.id not in related_ids:
            related_ids.insert(0, chunk.id)

        result: list[str] = []
        for entry_id in related_ids:
            if entry_id and entry_id not in result:
                result.append(entry_id)

        return result[:50]

    def _canonical_related_entry_ids(
        self,
        chunks: list[RagEvalEvidenceEntry],
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for chunk in chunks:
            if chunk.id:
                result[chunk.id] = self._chunk_related_ids(chunk)
        return result

    def _expand_related_entry_ids(
        self,
        entry_ids: list[str],
        *,
        valid_entry_ids: set[str],
        related_entry_ids_by_id: Mapping[str, list[str]],
    ) -> list[str]:
        result: list[str] = []

        for entry_id in entry_ids:
            if entry_id not in valid_entry_ids:
                continue

            related_ids = related_entry_ids_by_id.get(entry_id, [entry_id])
            for related_id in related_ids:
                if related_id in valid_entry_ids and related_id not in result:
                    result.append(related_id)

        return result[:50]

    def _eval_source_chunks(
        self, chunks: list[RagEvalEvidenceEntry]
    ) -> list[RagEvalEvidenceEntry]:
        groups_by_key: dict[tuple[str, str], list[RagEvalEvidenceEntry]] = {}
        ordered_keys: list[tuple[str, str]] = []

        for chunk in chunks:
            if not self._is_useful_chunk(chunk):
                continue

            group_key = self._eval_group_key(chunk)
            if group_key not in groups_by_key:
                groups_by_key[group_key] = []
                ordered_keys.append(group_key)
            groups_by_key[group_key].append(chunk)

        return [
            self._canonical_eval_chunk(groups_by_key[group_key])
            for group_key in ordered_keys
        ]

    def _eval_group_key(self, chunk: RagEvalEvidenceEntry) -> tuple[str, str]:
        entry_kind = self._metadata_text(chunk.metadata, "entry_kind") or "legacy"
        normalized_title = self._normalized_title(chunk.metadata.get("title"))
        if normalized_title:
            return (entry_kind, normalized_title)
        return (entry_kind, f"chunk:{chunk.id}")

    def _canonical_eval_chunk(
        self, chunks: list[RagEvalEvidenceEntry]
    ) -> RagEvalEvidenceEntry:
        primary = chunks[0]
        related_ids = [chunk.id for chunk in chunks if chunk.id]

        content_parts = [
            self._content_without_markdown_scaffold(
                chunk.content,
                chunk.metadata.get("title"),
            )
            for chunk in chunks
        ]
        compacted_content_parts = self._compact_overlapping_content_parts(content_parts)
        content = "\n\n".join(part for part in compacted_content_parts if part).strip()
        if not content:
            content = primary.content

        metadata = dict(primary.metadata)
        metadata["canonical_entry_id"] = primary.id
        metadata["related_entry_ids"] = related_ids
        metadata["merged_entry_count"] = len(chunks)
        metadata["compacted_source_part_count"] = len(compacted_content_parts)

        return RagEvalEvidenceEntry(
            id=primary.id,
            content=content,
            document_id=primary.document_id,
            source=primary.source,
            score=primary.score,
            metadata=metadata,
        )

    def _compact_overlapping_content_parts(
        self,
        content_parts: list[str],
    ) -> list[str]:
        normalized_parts = [
            (part, self._normalized_content_for_containment(part))
            for part in content_parts
            if part
        ]
        result: list[str] = []

        for index, (part, normalized) in enumerate(normalized_parts):
            if not normalized:
                continue

            is_contained_in_richer_part = False
            for other_index, (_, other_normalized) in enumerate(normalized_parts):
                if other_index == index or not other_normalized:
                    continue
                if len(other_normalized) <= len(normalized):
                    continue
                if len(normalized) < MIN_CONTAINED_EVAL_SOURCE_CHARS:
                    continue
                if normalized in other_normalized:
                    is_contained_in_richer_part = True
                    break

            if not is_contained_in_richer_part and part not in result:
                result.append(part)

        return result

    def _normalized_content_for_containment(self, value: str) -> str:
        normalized = self._normalized_for_quality(value)
        normalized = re.sub(r"[^0-9a-zа-яё]+", " ", normalized)
        return " ".join(normalized.split())

    def _is_useful_chunk(self, chunk: RagEvalEvidenceEntry) -> bool:
        if not chunk.id.strip():
            return False

        entry_kind = self._metadata_text(chunk.metadata, "entry_kind")
        if entry_kind and entry_kind not in EVAL_QUESTION_SOURCE_ENTRY_KINDS:
            return False

        content = " ".join(chunk.content.split())
        if not content:
            return False
        if content in {"---", "***", "___", "--", "-"}:
            return False
        if re.fullmatch(r"[-*_]{3,}", content):
            return False
        if content[0] in {",", ";", ":", ".", ")", "]"}:
            return False

        stripped_scaffold = self._content_without_markdown_scaffold(
            chunk.content,
            chunk.metadata.get("title"),
        )
        if len(stripped_scaffold) < MIN_EVAL_SOURCE_CONTENT_CHARS:
            return False

        return bool(re.search(r"[0-9A-Za-zА-Яа-яЁё]", stripped_scaffold))

    def _content_without_markdown_scaffold(
        self,
        value: str,
        title: object | None = None,
    ) -> str:
        lines: list[str] = []
        for line in value.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if re.match(r"^#{1,6}\s+", stripped):
                stripped = re.sub(r"^#{1,6}\s+", "", stripped).strip()

            stripped = re.sub(r"\s+[-*_]{3,}\s*$", "", stripped).strip()
            stripped = self._strip_leading_title_from_content(stripped, title)
            if not stripped:
                continue
            if re.fullmatch(r"[-*_]{3,}", stripped):
                continue

            lines.append(stripped)

        return " ".join(" ".join(lines).split())

    def _strip_leading_title_from_content(
        self,
        content: str,
        title: object | None,
    ) -> str:
        stripped = content.strip()
        if not stripped:
            return ""

        for variant in self._title_prefix_variants(title):
            if stripped.casefold().startswith(variant.casefold()):
                return stripped[len(variant) :].lstrip(" .:-—–")

        return stripped

    def _title_prefix_variants(self, title: object | None) -> list[str]:
        raw_title = str(title or "").strip()
        if not raw_title:
            return []

        without_markdown = re.sub(r"^#+\s*", "", raw_title).strip()
        without_number = re.sub(r"^\d+[.)\-:]*\s*", "", without_markdown).strip()

        result: list[str] = []
        for candidate in (raw_title, without_markdown, without_number):
            normalized = " ".join(candidate.split())
            if normalized and normalized not in result:
                result.append(normalized)

        return sorted(result, key=len, reverse=True)

    def _metadata_text(self, metadata: Mapping[str, object], key: str) -> str:
        return str(metadata.get(key) or "").strip()

    def _normalized_title(self, value: object) -> str:
        normalized = " ".join(str(value or "").casefold().replace("ё", "е").split())
        normalized = re.sub(r"^#+\s*", "", normalized)
        normalized = re.sub(r"^\d+[.)\-:]*\s*", "", normalized)
        return normalized.strip()

    def _batches(
        self, chunks: list[RagEvalEvidenceEntry]
    ) -> list[list[RagEvalEvidenceEntry]]:
        useful_chunks = [chunk for chunk in chunks if self._is_useful_chunk(chunk)]
        return [
            useful_chunks[index : index + MAX_ENTRIES_PER_LLM_BATCH]
            for index in range(0, len(useful_chunks), MAX_ENTRIES_PER_LLM_BATCH)
        ]

    def _clip(self, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) <= MAX_CHUNK_CHARS:
            return cleaned
        return cleaned[:MAX_CHUNK_CHARS].rstrip() + "…"
