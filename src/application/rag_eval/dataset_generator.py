from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import cast, get_args

from src.application.rag_eval.ports import RagEvalJsonLlmPort
from src.domain.project_plane.knowledge_retrieval_surface import (
    FORBIDDEN_PRODUCTION_ENTRY_TYPES,
    TRANSITIONAL_PRODUCTION_ENTRY_TYPES,
)
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
MIN_EVAL_SOURCE_CONTENT_CHARS = 16
MIN_CONTAINED_EVAL_SOURCE_CHARS = 24

EVAL_QUESTION_SOURCE_ENTRY_TYPES = TRANSITIONAL_PRODUCTION_ENTRY_TYPES
EXCLUDED_EVAL_SOURCE_ENTRY_TYPES = FORBIDDEN_PRODUCTION_ENTRY_TYPES


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
Generate real client/user questions about the product facts, not questions about
the source document structure.

Strictly forbidden:
- questions about section numbers, headings, fragments, paragraphs, first part,
  "what is written in section X", "is there section X";
- questions whose answer is merely that a section exists;
- questions asking where information is located in the document;
- questions copied from built-in test sections;
- near-duplicate questions that test the same fact many times.

Forbidden Russian shapes:
- "что сказано в разделе ..."
- "есть ли в документе раздел ..."
- "о чём речь в первой части ..."
- "в каком разделе указано ..."
- "где указано ..."
- "этот фрагмент ..."

If the chunk contains test questions, negative tests, preview checks, expected
topics, or RAG-search rules, do not treat that text as product facts for new
questions. Use it only as guidance for boundaries.

For one source fact generate at most:
- one direct question;
- one natural paraphrase;
- one risky/boundary question when useful.
"""


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

        eval_chunks = self._eval_source_chunks(chunks)
        batches = self._batches(eval_chunks)
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
        related_chunk_ids_by_id = self._canonical_related_chunk_ids(eval_chunks)

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
                    related_chunk_ids_by_id=related_chunk_ids_by_id,
                )
                if question is None:
                    continue

                if not is_document_structure_eval_question(question.question):
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
            "canonical_eval_unit_count": len(eval_chunks),
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
        source_chunk_ids = self._chunk_related_ids(chunk)
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
            return f"Какой практический факт нужно знать по теме «{title}»?"

        preview = " ".join(chunk.content.split())[:90].rstrip(" .,:;")
        if preview:
            return "Какой практический вывод следует из этой информации?"

        return "Какой практический факт содержит эта база знаний?"

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
            "- expected_answer_summary = compact user-facing business/product fact, not document-structure prose.",
            "- Do not generate questions about section numbers, headings, markdown structure, or whether the document contains a section.",
            "- Reject meta-document facts like 'Document contains a section titled ...' as eval targets.",
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
        related_chunk_ids_by_id: Mapping[str, list[str]],
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

        expected_chunk_ids = self._expand_related_chunk_ids(
            self._string_list(payload.get("expected_chunk_ids")),
            valid_chunk_ids=valid_chunk_ids,
            related_chunk_ids_by_id=related_chunk_ids_by_id,
        )

        raw_should_answer = payload.get("should_answer")
        should_answer = (
            raw_should_answer
            if isinstance(raw_should_answer, bool)
            else bool(expected_chunk_ids)
        )

        if should_answer and not expected_chunk_ids:
            return None

        metadata = self._metadata(payload.get("metadata"))
        source_chunk_ids = self._expand_related_chunk_ids(
            self._string_list(metadata.get("source_chunk_ids")),
            valid_chunk_ids=valid_chunk_ids,
            related_chunk_ids_by_id=related_chunk_ids_by_id,
        )
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

        expected_answer_summary = str(
            payload.get("expected_answer_summary") or ""
        ).strip()[:1200]

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
            question_type=cast(RagEvalQuestionType, question_type),
            expected_chunk_ids=expected_chunk_ids,
            expected_answer_summary=expected_answer_summary,
            should_answer=bool(should_answer),
            should_escalate=bool(payload.get("should_escalate")),
            difficulty=self._difficulty(payload.get("difficulty")),
            severity=cast(RagEvalSeverity, severity),
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

    def _chunk_related_ids(self, chunk: RagEvalChunk) -> list[str]:
        related_ids = self._string_list(chunk.metadata.get("related_chunk_ids"))
        if chunk.id and chunk.id not in related_ids:
            related_ids.insert(0, chunk.id)

        result: list[str] = []
        for chunk_id in related_ids:
            if chunk_id and chunk_id not in result:
                result.append(chunk_id)

        return result[:50]

    def _canonical_related_chunk_ids(
        self,
        chunks: list[RagEvalChunk],
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for chunk in chunks:
            if chunk.id:
                result[chunk.id] = self._chunk_related_ids(chunk)
        return result

    def _expand_related_chunk_ids(
        self,
        chunk_ids: list[str],
        *,
        valid_chunk_ids: set[str],
        related_chunk_ids_by_id: Mapping[str, list[str]],
    ) -> list[str]:
        result: list[str] = []

        for chunk_id in chunk_ids:
            if chunk_id not in valid_chunk_ids:
                continue

            related_ids = related_chunk_ids_by_id.get(chunk_id, [chunk_id])
            for related_id in related_ids:
                if related_id in valid_chunk_ids and related_id not in result:
                    result.append(related_id)

        return result[:50]

    def _eval_source_chunks(self, chunks: list[RagEvalChunk]) -> list[RagEvalChunk]:
        groups_by_key: dict[tuple[str, str], list[RagEvalChunk]] = {}
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

    def _eval_group_key(self, chunk: RagEvalChunk) -> tuple[str, str]:
        entry_type = self._metadata_text(chunk.metadata, "entry_type") or "legacy"
        normalized_title = self._normalized_title(chunk.metadata.get("title"))
        if normalized_title:
            return (entry_type, normalized_title)
        return (entry_type, f"chunk:{chunk.id}")

    def _canonical_eval_chunk(self, chunks: list[RagEvalChunk]) -> RagEvalChunk:
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
        metadata["canonical_chunk_id"] = primary.id
        metadata["related_chunk_ids"] = related_ids
        metadata["merged_chunk_count"] = len(chunks)
        metadata["compacted_source_part_count"] = len(compacted_content_parts)

        return RagEvalChunk(
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

    def _is_useful_chunk(self, chunk: RagEvalChunk) -> bool:
        if not chunk.id.strip():
            return False

        entry_type = self._metadata_text(chunk.metadata, "entry_type")
        if entry_type and entry_type not in EVAL_QUESTION_SOURCE_ENTRY_TYPES:
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
