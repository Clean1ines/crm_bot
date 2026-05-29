import asyncio
import hashlib
import json
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast


from src.application.errors import (
    EmbeddingProviderError,
    KnowledgeDocumentDeletedDuringProcessingError,
    ValidationError,
)
from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.ports.commercial_price_acquisition import (
    CommercialPriceAcquisitionServicePort,
)
from src.application.ports.knowledge import (
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeCompilationTracePort,
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    KnowledgeRuntimeRetrievalPort,
)
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    ModelUsageRepositoryFactoryPort,
    KnowledgePreprocessorFactoryPort,
)
from src.application.ports.logger_port import LoggerPort
from src.application.services.commercial_price_ingestion_service import (
    CommercialPriceIngestionService,
)
from src.application.services.knowledge_answer_compiler_batching import (
    KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL,
    KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET,
    _technical_chunk_batches_for_answer_compiler,
)
from src.application.services.knowledge_canonical_publication_builder import (
    _CompiledAnswerEntryDraft,
    _answer_topic_key,
    _source_refs_for_compiled_answer_draft,
    canonical_entries_from_preprocessing_result,
    canonical_entries_from_raw_answer_candidates,
)
from src.application.services.knowledge_generated_entry_repair import (
    repair_generated_entry,
)
from src.application.services.knowledge_answer_resolution_service import (
    KnowledgeAnswerResolutionService,
    _merge_answer_text as _answer_resolution_service_merge_answer_text,
    _merge_source_excerpt_text as _answer_resolution_service_merge_source_excerpt_text,
    _limit_compiled_text as _answer_resolution_service_limit_compiled_text,
    _merge_limited_text_tuple_values as _answer_resolution_service_merge_limited_text_tuple_values,
    _merge_entry_fields_deterministically as _answer_resolution_service_merge_entry_fields_deterministically,
    _answer_resolution_candidate_id as _answer_resolution_service_answer_resolution_candidate_id,
    _answer_resolution_candidate_index as _answer_resolution_service_answer_resolution_candidate_index,
    _answer_resolution_tokens_from_text as _answer_resolution_service_answer_resolution_tokens_from_text,
    _answer_resolution_entry_text as _answer_resolution_service_answer_resolution_entry_text,
    _answer_resolution_entry_tokens as _answer_resolution_service_answer_resolution_entry_tokens,
    _answer_resolution_token_similarity as _answer_resolution_service_answer_resolution_token_similarity,
    _answer_resolution_token_overlap_coverage as _answer_resolution_service_answer_resolution_token_overlap_coverage,
    _answer_resolution_primary_intent_tokens as _answer_resolution_service_answer_resolution_primary_intent_tokens,
    _answer_resolution_same_intent_summary_score as _answer_resolution_service_answer_resolution_same_intent_summary_score,
    _answer_resolution_question_intent_text as _answer_resolution_service_answer_resolution_question_intent_text,
    _answer_resolution_question_intent_tokens as _answer_resolution_service_answer_resolution_question_intent_tokens,
    _answer_resolution_entry_pair_score as _answer_resolution_service_answer_resolution_entry_pair_score,
    _answer_resolution_entries_are_suspects as _answer_resolution_service_answer_resolution_entries_are_suspects,
    _answer_resolution_limited_text_tuple as _answer_resolution_service_answer_resolution_limited_text_tuple,
    _answer_resolution_candidate_from_entry as _answer_resolution_service_answer_resolution_candidate_from_entry,
    _answer_resolution_question_intent as _answer_resolution_service_answer_resolution_question_intent,
    _answer_resolution_suspect_pairs_from_entries as _answer_resolution_service_answer_resolution_suspect_pairs_from_entries,
    _answer_resolution_case_components_from_pairs as _answer_resolution_service_answer_resolution_case_components_from_pairs,
    _answer_resolution_cases_from_entries as _answer_resolution_service_answer_resolution_cases_from_entries,
    _answer_resolution_survivor_index as _answer_resolution_service_answer_resolution_survivor_index,
    _answer_resolution_text_fingerprint as _answer_resolution_service_answer_resolution_text_fingerprint,
    _answer_resolution_text_units as _answer_resolution_service_answer_resolution_text_units,
    _answer_unit_fingerprint as _answer_resolution_service_answer_unit_fingerprint,
    _answer_units_by_fingerprint as _answer_resolution_service_answer_units_by_fingerprint,
    _merge_answer_units_deterministically as _answer_resolution_service_merge_answer_units_deterministically,
    _cleanup_answer_resolution_text_with_metrics as _answer_resolution_service_cleanup_answer_resolution_text_with_metrics,
    _cleanup_answer_resolution_text as _answer_resolution_service_cleanup_answer_resolution_text,
    _answer_resolution_decision_is_too_noisy as _answer_resolution_service_answer_resolution_decision_is_too_noisy,
    _reject_noisy_answer_resolution_decisions as _answer_resolution_service_reject_noisy_answer_resolution_decisions,
    _entry_with_answer_resolution_decision as _answer_resolution_service_entry_with_answer_resolution_decision,
    _answer_resolution_decision_is_publishable as _answer_resolution_service_answer_resolution_decision_is_publishable,
    _answer_resolution_text_language_hint as _answer_resolution_service_answer_resolution_text_language_hint,
    _answer_resolution_component_language_hint as _answer_resolution_service_answer_resolution_component_language_hint,
    _apply_answer_resolution_decisions as _answer_resolution_service_apply_answer_resolution_decisions,
    _answer_resolution_candidate_trace_payload as _answer_resolution_service_answer_resolution_candidate_trace_payload,
    _answer_resolution_trace_row as _answer_resolution_service_answer_resolution_trace_row,
    _answer_resolution_decisions_with_case_candidate_ids as _answer_resolution_service_answer_resolution_decisions_with_case_candidate_ids,
    _resolve_compiled_answer_cases as _answer_resolution_service_resolve_compiled_answer_cases,
)
from src.application.services.knowledge_normalization_service import (
    KnowledgeNormalizationService,
)
from src.application.services.knowledge_source_material_builder import (
    _chunk_content,
    _compiler_source_chunks_for_preprocessing,
    _indexable_chunks,
    _is_markdown_file,
    _json_array_field_item_count,
    _json_chunks_from_source_chunks,
    _source_chunk_optional_int,
    _source_chunks_from_json_chunks,
)
from src.domain.project_plane.knowledge_artifact_cleanup import (
    KnowledgeArtifactCleanupPlan,
    KnowledgeArtifactCleanupResult,
    build_document_reset_cleanup_plan,
)
from src.domain.project_plane.json_types import (
    JsonObject,
    JsonValue,
)
from src.domain.project_plane.embedding_text import CANONICAL_EMBEDDING_TEXT_VERSION
from src.domain.project_plane.knowledge_chunks import (
    KnowledgeChunk,
    KnowledgeChunkDraft,
    KnowledgeChunkRole,
    KnowledgeSectionPath,
)
from src.domain.project_plane.knowledge_document_structure import (
    KnowledgeDocumentBlock,
    KnowledgeDocumentSource,
    ParsedKnowledgeDocument,
)
from src.domain.project_plane.knowledge_semantic_builder import (
    build_knowledge_chunk_drafts,
    canonicalize_knowledge_chunk_drafts,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    MODE_PRICE_LIST,
    PREPROCESSING_STATUS_COMPLETED,
    PREPROCESSING_STATUS_FAILED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingResult,
    KnowledgePreprocessingValidationError,
    normalize_preprocessing_mode,
    KnowledgeAnswerResolutionDecision,
    prompt_version_for_mode,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate
from src.domain.project_plane.knowledge_compilation import (
    CompilerRunStatus,
    CompilerRun,
    CompilationMetrics,
    CompilerBatch,
    CompilerBatchStatus,
    CandidateClusterStatus,
    CandidateCluster,
    AnswerCandidateStatus,
    AnswerCandidate,
    CanonicalKnowledgeEntry,
    EmbeddingText,
    KnowledgeEnrichment,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceChunk,
    SourceRef,
)


class KnowledgeIngestionRepositoryPort(
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeCompilationTracePort,
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    KnowledgeRuntimeRetrievalPort,
    Protocol,
):
    """Repository subset required by knowledge ingestion workflows."""

    async def cleanup_document_artifacts(
        self,
        plan: KnowledgeArtifactCleanupPlan,
    ) -> KnowledgeArtifactCleanupResult: ...


class CommercialPriceAcquisitionServiceFactoryPort(Protocol):
    def __call__(self) -> CommercialPriceAcquisitionServicePort: ...


class CommercialPriceRepositoryFactoryPort(Protocol):
    def __call__(self, pool: KnowledgeDbPoolPort) -> CommercialPriceKnowledgePort: ...


class KnowledgeIngestionRepositoryFactoryPort(Protocol):
    def __call__(
        self, pool: KnowledgeDbPoolPort
    ) -> KnowledgeIngestionRepositoryPort: ...


_PLAIN_CHUNK_AUDIT_FIELDS: tuple[str, ...] = (
    "content",
    "entry_kind",
    "title",
    "source_excerpt",
    "questions",
    "synonyms",
    "tags",
    "embedding_text",
)

SEMANTIC_CHUNK_METADATA_FIELDS = (
    "title",
    "source_excerpt",
    "questions",
    "synonyms",
    "tags",
    "embedding_text",
)


def _present_plain_chunk_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _plain_chunk_field_counts(chunks: list[JsonObject]) -> dict[str, int]:
    return {
        field: sum(
            1 for chunk in chunks if _present_plain_chunk_value(chunk.get(field))
        )
        for field in _PLAIN_CHUNK_AUDIT_FIELDS
    }


def _log_plain_chunk_audit(
    logger: LoggerPort,
    *,
    project_id: str,
    document_id: str,
    chunks: list[JsonObject],
    context: str,
) -> None:
    logger.info(
        "Knowledge plain chunk persistence audit",
        extra={
            "project_id": project_id,
            "document_id": document_id,
            "context": context,
            "chunk_count": len(chunks),
            "field_counts": _plain_chunk_field_counts(chunks),
            "embedding_input": "embedding_text_or_content",
            "metadata_preserved": True,
        },
    )


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentProcessingResult:
    document_id: str
    preprocessing_status: str
    structured_entries: int


def _clean_optional_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, tuple):
        candidates = value
    elif isinstance(value, list):
        candidates = tuple(value)
    else:
        return ()

    result: list[str] = []
    for item in candidates:
        cleaned = _clean_optional_text(item)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _has_semantic_chunk_metadata(chunk: JsonObject) -> bool:
    entry_kind = _clean_optional_text(chunk.get("entry_kind"))
    if entry_kind:
        return True

    content = _chunk_content(chunk)
    for field in SEMANTIC_CHUNK_METADATA_FIELDS:
        value = chunk.get(field)
        if field == "embedding_text":
            embedding_text = _clean_optional_text(value)
            if embedding_text and embedding_text != content:
                return True
            continue
        if _present_plain_chunk_value(value):
            return True

    return False


def _role_from_entry_kind(value: object) -> KnowledgeChunkRole:
    text = _clean_optional_text(value)
    if not text:
        return KnowledgeChunkRole.ANSWER_KNOWLEDGE

    try:
        return KnowledgeChunkRole(text)
    except ValueError:
        return KnowledgeChunkRole.ANSWER_KNOWLEDGE


def _draft_from_json_chunk(
    chunk: JsonObject,
    *,
    file_name: str,
) -> KnowledgeChunkDraft | None:
    content = _chunk_content(chunk)
    if not content:
        return None

    title = _clean_optional_text(chunk.get("title"))
    headings = (title,) if title else ()
    metadata: dict[str, object] = {}
    metadata_fields = {
        "content",
        "entry_kind",
        "title",
        "source_excerpt",
        "questions",
        "synonyms",
        "tags",
        "embedding_text",
    }
    for key, value in chunk.items():
        if key not in metadata_fields:
            metadata[key] = value

    return KnowledgeChunkDraft(
        content=content,
        role=_role_from_entry_kind(chunk.get("entry_kind")),
        title=title,
        source_excerpt=_clean_optional_text(chunk.get("source_excerpt")),
        section_path=KnowledgeSectionPath(
            document_title=file_name,
            headings=headings,
        ),
        questions=_text_tuple(chunk.get("questions")),
        synonyms=_text_tuple(chunk.get("synonyms")),
        tags=_text_tuple(chunk.get("tags")),
        embedding_text=_clean_optional_text(chunk.get("embedding_text")),
        metadata=metadata,
    )


def _document_from_json_chunks(
    *,
    file_name: str,
    chunks: list[JsonObject],
) -> ParsedKnowledgeDocument:
    drafts: list[KnowledgeChunkDraft] = []
    blocks: list[KnowledgeDocumentBlock] = []

    for chunk in chunks:
        if _has_semantic_chunk_metadata(chunk):
            draft = _draft_from_json_chunk(chunk, file_name=file_name)
            if draft is not None:
                drafts.append(draft)
            continue

        content = _chunk_content(chunk)
        if not content:
            continue

        block = KnowledgeDocumentBlock(content=content)
        blocks.append(block)
        drafts.extend(
            build_knowledge_chunk_drafts(
                document_title=file_name,
                blocks=(block,),
            )
        )

    canonical_drafts = canonicalize_knowledge_chunk_drafts(
        document_title=file_name,
        drafts=tuple(drafts),
    )

    return ParsedKnowledgeDocument(
        source=KnowledgeDocumentSource(filename=file_name),
        title=file_name,
        chunks=canonical_drafts,
        blocks=tuple(blocks),
    )


def _raw_chunks_for_structured_persistence(
    chunks: list[JsonObject],
) -> list[JsonObject]:
    """Preserve source chunks when LLM preprocessing enriches a document.

    LLM preprocessing may add normalized FAQ/price/instruction entries, but it
    must never be the only persisted representation of the uploaded document.

    Important: source chunks may already be enriched by the deterministic
    chunker. Do not collapse them back to legacy raw chunk rows,
    otherwise markdown titles, source excerpts, tags and embedding_text are
    lost in FAQ/structured preprocessing modes.
    """
    raw_chunks: list[JsonObject] = []
    metadata_fields = (
        "entry_kind",
        "title",
        "source_excerpt",
        "questions",
        "synonyms",
        "tags",
        "embedding_text",
    )

    for chunk in chunks:
        content = _chunk_content(chunk)
        if not content:
            continue

        preserved: JsonObject = {"content": content}
        for field in metadata_fields:
            if field not in chunk:
                continue

            value = chunk[field]
            if field in {"questions", "synonyms", "tags"}:
                preserved[field] = value
                continue

            if _present_plain_chunk_value(value):
                preserved[field] = value

        if not _present_plain_chunk_value(preserved.get("entry_kind")):
            preserved["entry_kind"] = "answer"

        if not _present_plain_chunk_value(preserved.get("embedding_text")):
            preserved["embedding_text"] = content

        raw_chunks.append(preserved)

    return raw_chunks


def _combined_chunks_for_canonical_persistence(
    *,
    raw_chunks: list[JsonObject],
    structured_chunks: list[JsonObject],
) -> list[JsonObject]:
    """Combine raw and structured chunks; semantic merging belongs to domain builder."""

    combined: list[JsonObject] = []
    combined.extend(_raw_chunks_for_structured_persistence(raw_chunks))
    combined.extend(structured_chunks)
    return combined


def _merged_preprocessing_result(
    *,
    mode: KnowledgePreprocessingMode,
    results: Sequence[KnowledgePreprocessingResult],
) -> KnowledgePreprocessingResult:
    if not results:
        raise ValidationError("Knowledge preprocessing produced no compiler results")

    entries: list[KnowledgePreprocessingEntry] = []
    metrics: JsonObject = {
        "technical_compiler_call_count": len(results),
        "technical_chunk_batch_size": KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL,
    }

    for index, result in enumerate(results):
        entries.extend(result.entries)
        metrics[f"technical_call_{index}_entry_count"] = len(result.entries)

    latest = results[-1]
    return KnowledgePreprocessingResult(
        mode=mode,
        prompt_version=latest.prompt_version,
        model=latest.model,
        entries=tuple(entries),
        metrics=metrics,
    )


def _answer_titles_from_preprocessing_results(
    *,
    mode: KnowledgePreprocessingMode,
    results: Sequence[KnowledgePreprocessingResult],
) -> tuple[str, ...]:
    if not results:
        return ()

    merged_result = _merged_preprocessing_result(mode=mode, results=results)
    drafts = _compiled_answer_drafts_from_preprocessing_result(merged_result)
    titles: list[str] = []

    for draft in drafts:
        title = _clean_optional_text(draft.title)
        if title and title not in titles:
            titles.append(title)

    return tuple(titles[-KCD_STAGE_K_PREVIOUS_TITLE_LIMIT:])


KCD_STAGE_CD_COMPILER_VERSION = "kcd_v1_stage_cd"
KCD_STAGE_E_COMPILER_VERSION = "kcd_v1_stage_e"
KCD_STAGE_K_COMPILER_VERSION = "kcd_v1_stage_k_answer_compiler"
KCD_STAGE_K_CANCELLED_ERROR = "Knowledge preprocessing cancelled by operator"
KCD_STAGE_K_PREVIOUS_TITLE_LIMIT = 80
KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS = 220


_canonical_entries_from_preprocessing_result = (
    canonical_entries_from_preprocessing_result
)
_canonical_entries_from_raw_answer_candidates = (
    canonical_entries_from_raw_answer_candidates
)


_repair_generated_entry = repair_generated_entry


_merge_answer_text = _answer_resolution_service_merge_answer_text
_merge_source_excerpt_text = _answer_resolution_service_merge_source_excerpt_text
_limit_compiled_text = _answer_resolution_service_limit_compiled_text
_merge_limited_text_tuple_values = (
    _answer_resolution_service_merge_limited_text_tuple_values
)
_merge_entry_fields_deterministically = (
    _answer_resolution_service_merge_entry_fields_deterministically
)
_answer_resolution_candidate_id = (
    _answer_resolution_service_answer_resolution_candidate_id
)
_answer_resolution_candidate_index = (
    _answer_resolution_service_answer_resolution_candidate_index
)
_answer_resolution_tokens_from_text = (
    _answer_resolution_service_answer_resolution_tokens_from_text
)
_answer_resolution_entry_text = _answer_resolution_service_answer_resolution_entry_text
_answer_resolution_entry_tokens = (
    _answer_resolution_service_answer_resolution_entry_tokens
)
_answer_resolution_token_similarity = (
    _answer_resolution_service_answer_resolution_token_similarity
)
_answer_resolution_token_overlap_coverage = (
    _answer_resolution_service_answer_resolution_token_overlap_coverage
)
_answer_resolution_primary_intent_tokens = (
    _answer_resolution_service_answer_resolution_primary_intent_tokens
)
_answer_resolution_same_intent_summary_score = (
    _answer_resolution_service_answer_resolution_same_intent_summary_score
)
_answer_resolution_question_intent_text = (
    _answer_resolution_service_answer_resolution_question_intent_text
)
_answer_resolution_question_intent_tokens = (
    _answer_resolution_service_answer_resolution_question_intent_tokens
)
_answer_resolution_entry_pair_score = (
    _answer_resolution_service_answer_resolution_entry_pair_score
)
_answer_resolution_entries_are_suspects = (
    _answer_resolution_service_answer_resolution_entries_are_suspects
)
_answer_resolution_limited_text_tuple = (
    _answer_resolution_service_answer_resolution_limited_text_tuple
)
_answer_resolution_candidate_from_entry = (
    _answer_resolution_service_answer_resolution_candidate_from_entry
)
_answer_resolution_question_intent = (
    _answer_resolution_service_answer_resolution_question_intent
)
_answer_resolution_suspect_pairs_from_entries = (
    _answer_resolution_service_answer_resolution_suspect_pairs_from_entries
)
_answer_resolution_case_components_from_pairs = (
    _answer_resolution_service_answer_resolution_case_components_from_pairs
)
_answer_resolution_cases_from_entries = (
    _answer_resolution_service_answer_resolution_cases_from_entries
)
_answer_resolution_survivor_index = (
    _answer_resolution_service_answer_resolution_survivor_index
)
_answer_resolution_text_fingerprint = (
    _answer_resolution_service_answer_resolution_text_fingerprint
)
_answer_resolution_text_units = _answer_resolution_service_answer_resolution_text_units
_answer_unit_fingerprint = _answer_resolution_service_answer_unit_fingerprint
_answer_units_by_fingerprint = _answer_resolution_service_answer_units_by_fingerprint
_merge_answer_units_deterministically = (
    _answer_resolution_service_merge_answer_units_deterministically
)
_cleanup_answer_resolution_text_with_metrics = (
    _answer_resolution_service_cleanup_answer_resolution_text_with_metrics
)
_cleanup_answer_resolution_text = (
    _answer_resolution_service_cleanup_answer_resolution_text
)
_answer_resolution_decision_is_too_noisy = (
    _answer_resolution_service_answer_resolution_decision_is_too_noisy
)
_reject_noisy_answer_resolution_decisions = (
    _answer_resolution_service_reject_noisy_answer_resolution_decisions
)
_entry_with_answer_resolution_decision = (
    _answer_resolution_service_entry_with_answer_resolution_decision
)
_answer_resolution_decision_is_publishable = (
    _answer_resolution_service_answer_resolution_decision_is_publishable
)
_answer_resolution_text_language_hint = (
    _answer_resolution_service_answer_resolution_text_language_hint
)
_answer_resolution_component_language_hint = (
    _answer_resolution_service_answer_resolution_component_language_hint
)
_apply_answer_resolution_decisions = (
    _answer_resolution_service_apply_answer_resolution_decisions
)
_answer_resolution_candidate_trace_payload = (
    _answer_resolution_service_answer_resolution_candidate_trace_payload
)
_answer_resolution_trace_row = _answer_resolution_service_answer_resolution_trace_row
_answer_resolution_decisions_with_case_candidate_ids = (
    _answer_resolution_service_answer_resolution_decisions_with_case_candidate_ids
)
_resolve_compiled_answer_cases = (
    _answer_resolution_service_resolve_compiled_answer_cases
)


def _source_excerpt_to_text(value: object) -> str:
    if isinstance(value, tuple):
        return "\n\n".join(
            _clean_optional_text(str(part))
            for part in value
            if _clean_optional_text(str(part))
        )
    return _clean_optional_text(str(value or ""))


def _regenerate_entry_from_source_excerpt(
    entry: KnowledgePreprocessingEntry, source_excerpt: str
) -> KnowledgePreprocessingEntry:
    sanitized_source = "\n".join(
        line
        for line in source_excerpt.splitlines()
        if not line.lstrip().startswith("#")
    ).strip()
    rebuilt_answer = _answer_digest(
        sanitized_source or source_excerpt,
        max_chars=KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS,
    )
    rebuilt = KnowledgePreprocessingEntry(
        title=entry.title,
        answer=rebuilt_answer,
        source_excerpt=source_excerpt or entry.source_excerpt,
        questions=entry.questions,
        synonyms=entry.synonyms,
        tags=entry.tags,
        embedding_text=entry.embedding_text,
        canonical_question=entry.canonical_question,
        source_chunk_indexes=entry.source_chunk_indexes,
    )
    return rebuilt


def _preprocessing_failure_status_message(exc: Exception) -> str:
    if str(exc) == KCD_STAGE_K_CANCELLED_ERROR:
        return (
            "Обработка остановлена: прогресс до последнего завершённого шага сохранён"
        )
    if isinstance(exc, KnowledgePreprocessingValidationError):
        return "Ошибка предобработки: LLM вернула данные в неподдерживаемом формате"
    if isinstance(exc, ValidationError):
        return "Ошибка предобработки: результаты не прошли проверку перед публикацией"
    if isinstance(exc, json.JSONDecodeError):
        return "Ошибка предобработки: LLM не вернула корректный JSON"
    return "Ошибка предобработки: pipeline остановлен до публикации результатов"


def _answer_digest(
    value: str, *, max_chars: int = KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS
) -> str:
    text = _clean_optional_text(value)
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars].rsplit(" ", 1)[0].strip()
    return trimmed or text[:max_chars].strip()


def _question_intent_primary_question(entry: KnowledgePreprocessingEntry) -> str:
    if entry.canonical_question:
        return entry.canonical_question
    for question in _text_tuple(entry.questions):
        if question:
            return question
    return _answer_digest(entry.answer)


def _question_intent_tokens_from_entry(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    return _answer_resolution_tokens_from_text(
        " ".join(
            part
            for part in (
                _question_intent_primary_question(entry),
                " ".join(_text_tuple(entry.questions)),
                _answer_digest(entry.answer),
            )
            if part
        )
    )


def _preprocessing_entry_from_technical_chunk(
    chunk: JsonObject,
) -> KnowledgePreprocessingEntry:
    content = _clean_optional_text(str(chunk.get("content") or ""))
    title = _clean_optional_text(str(chunk.get("title") or "")) or content[:80]
    return KnowledgePreprocessingEntry(
        title=title or "technical source chunk",
        answer=_answer_digest(content),
        source_excerpt=content,
        questions=_text_tuple(chunk.get("questions")),
        synonyms=(),
        tags=(),
        embedding_text=_clean_optional_text(
            str(chunk.get("embedding_text") or content)
        ),
        canonical_question=_clean_optional_text(
            str(chunk.get("canonical_question") or "")
        ),
    )


def _entry_kind_from_chunk_role(role: KnowledgeChunkRole) -> KnowledgeEntryKind:
    try:
        return KnowledgeEntryKind(role.value)
    except ValueError:
        return KnowledgeEntryKind.ANSWER


def _canonical_entry_stable_key(
    *,
    document_id: str,
    index: int,
    chunk: KnowledgeChunk,
) -> str:
    digest = hashlib.sha256(
        f"{document_id}:{index}:{chunk.role.value}:{chunk.title}:{chunk.content}".encode(
            "utf-8"
        )
    ).hexdigest()
    return f"{document_id}:{index}:{digest[:24]}"


def _source_chunk_for_knowledge_chunk(
    *,
    chunk: KnowledgeChunk,
    index: int,
    source_chunks: Sequence[SourceChunk],
) -> SourceChunk:
    if not source_chunks:
        raise ValidationError("Cannot create canonical entry without source chunks")

    excerpt = _clean_optional_text(chunk.source_excerpt)
    if excerpt:
        for source_chunk in source_chunks:
            if excerpt in source_chunk.content or source_chunk.content in excerpt:
                return source_chunk

    if index < len(source_chunks):
        return source_chunks[index]

    return source_chunks[0]


def _canonical_source_ref(
    *,
    chunk: KnowledgeChunk,
    source_chunk: SourceChunk,
) -> SourceRef:
    quote = _clean_optional_text(chunk.source_excerpt) or source_chunk.content
    return SourceRef(
        source_index=source_chunk.source_index,
        quote=quote,
        source_chunk_id=source_chunk.id,
        start_offset=source_chunk.start_offset,
        end_offset=source_chunk.end_offset,
        confidence=1.0,
    )


def _source_chunk_for_technical_chunk(
    *,
    technical_chunk: JsonObject,
    source_chunks: Sequence[SourceChunk],
) -> SourceChunk | None:
    if not source_chunks:
        return None

    raw_index = _source_chunk_optional_int(technical_chunk.get("index"))
    if raw_index is not None:
        for source_chunk in source_chunks:
            if source_chunk.source_index == raw_index:
                return source_chunk

    content = _chunk_content(technical_chunk)
    if content:
        for source_chunk in source_chunks:
            if content in source_chunk.content or source_chunk.content in content:
                return source_chunk

    return None


def _compiler_batch_id(*, compiler_run_id: str, batch_index: int) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{compiler_run_id}:technical-batch:{batch_index}",
        )
    )


def _compiler_batches_from_technical_batches(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    technical_batches: Sequence[Sequence[JsonObject]],
    source_chunks: Sequence[SourceChunk],
) -> tuple[CompilerBatch, ...]:
    batch_count = len(technical_batches)
    batches: list[CompilerBatch] = []

    for batch_index, technical_batch in enumerate(technical_batches, start=1):
        batch_source_chunks: list[SourceChunk] = []
        for technical_chunk in technical_batch:
            source_chunk = _source_chunk_for_technical_chunk(
                technical_chunk=technical_chunk,
                source_chunks=source_chunks,
            )
            if source_chunk is not None and source_chunk not in batch_source_chunks:
                batch_source_chunks.append(source_chunk)

        batches.append(
            CompilerBatch(
                id=_compiler_batch_id(
                    compiler_run_id=compiler_run_id,
                    batch_index=batch_index,
                ),
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                batch_index=batch_index,
                batch_count=batch_count,
                source_chunk_ids=tuple(chunk.id for chunk in batch_source_chunks),
                source_chunk_indexes=tuple(
                    chunk.source_index for chunk in batch_source_chunks
                ),
                status=CompilerBatchStatus.PENDING,
                metadata={
                    "stage": "stage_k_technical_compiler_loop",
                    "technical_chunk_count": len(technical_batch),
                },
            )
        )

    return tuple(batches)


def _raw_answer_candidate_id(
    *,
    compiler_run_id: str,
    batch_index: int,
    fragment_index: int,
) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{compiler_run_id}:batch:{batch_index}:fragment:{fragment_index}",
        )
    )


def _raw_answer_candidates_from_preprocessing_entries(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    batch_id: str,
    batch_index: int,
    entries: Sequence[KnowledgePreprocessingEntry],
    source_chunks: Sequence[SourceChunk],
    mode: KnowledgePreprocessingMode,
) -> tuple[AnswerCandidate, ...]:
    candidates: list[AnswerCandidate] = []

    for fragment_index, entry in enumerate(entries, start=1):
        draft = _preprocessing_entry_to_compiled_draft(
            entry,
            mode=mode,
            index=fragment_index - 1,
        )
        if not draft.answer:
            continue

        candidates.append(
            AnswerCandidate(
                id=_raw_answer_candidate_id(
                    compiler_run_id=compiler_run_id,
                    batch_index=batch_index,
                    fragment_index=fragment_index,
                ),
                document_id=document_id,
                project_id=project_id,
                compiler_run_id=compiler_run_id,
                topic_key=_answer_topic_key(entry, index=fragment_index - 1),
                title=draft.title,
                candidate_answer=draft.answer,
                source_refs=_source_refs_for_compiled_answer_draft(
                    draft=draft,
                    source_chunks=source_chunks,
                ),
                confidence=1.0 if draft.source_excerpts else None,
                status=AnswerCandidateStatus.EXTRACTED,
                metadata={
                    "stage": "stage_k_raw_extraction",
                    "batch_id": batch_id,
                    "batch_index": batch_index,
                    "fragment_index": fragment_index,
                    "canonical_question": entry.canonical_question,
                    "question_variants": list(entry.questions),
                    "synonyms": list(entry.synonyms),
                    "tags": list(entry.tags),
                    "source_chunk_indexes": list(entry.source_chunk_indexes),
                },
            )
        )

    return tuple(candidates)


def _normalized_answer_topic_key(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def _merge_text_tuple_values(
    *groups: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    for group in groups:
        for value in group:
            cleaned = _clean_optional_text(value)
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return tuple(result)


def _merge_int_tuple_values(*groups: tuple[int, ...]) -> tuple[int, ...]:
    result: list[int] = []
    for group in groups:
        for value in group:
            if value not in result:
                result.append(value)
    return tuple(result)


def _source_excerpts_from_preprocessing_entry(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    normalized = entry.source_excerpt.replace("\r\n", "\n").replace("\r", "\n")
    parts = tuple(part.strip() for part in normalized.split("\n\n"))
    return _text_tuple(parts)


def _preprocessing_entry_to_compiled_draft(
    entry: KnowledgePreprocessingEntry,
    *,
    mode: KnowledgePreprocessingMode,
    index: int,
) -> _CompiledAnswerEntryDraft:
    return _CompiledAnswerEntryDraft(
        title=_clean_optional_text(entry.title) or f"Answer entry {index + 1}",
        answer=_clean_optional_text(entry.answer),
        source_excerpts=_source_excerpts_from_preprocessing_entry(entry),
        source_refs=tuple(
            SourceRef(
                source_index=index,
                quote=source_excerpt,
                source_chunk_id=None,
                confidence=1.0,
            )
            for source_excerpt in _source_excerpts_from_preprocessing_entry(entry)
        ),
        questions=_text_tuple(entry.questions),
        synonyms=_text_tuple(entry.synonyms),
        tags=_text_tuple(entry.tags),
        embedding_text=_clean_optional_text(entry.embedding_text),
        metadata={
            "compiler_stage": "stage_k_answer_compiler",
            "preprocessing_mode": mode,
            "preprocessing_entry_indices": (index,),
        },
    )


def _merge_compiled_source_refs(
    first: tuple[SourceRef, ...],
    second: tuple[SourceRef, ...],
) -> tuple[SourceRef, ...]:
    refs: list[SourceRef] = []
    seen: set[tuple[int | None, str, str | None]] = set()

    for source_ref in (*first, *second):
        key = (
            source_ref.source_index,
            source_ref.quote,
            source_ref.source_chunk_id,
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(source_ref)

    return tuple(refs)


def _source_refs_from_compiled_answer_draft(
    draft: _CompiledAnswerEntryDraft,
    *,
    fallback_source_index: int,
) -> tuple[SourceRef, ...]:
    if draft.source_refs:
        return draft.source_refs

    return tuple(
        SourceRef(
            source_index=fallback_source_index,
            quote=source_excerpt,
            source_chunk_id=None,
            confidence=1.0,
        )
        for source_excerpt in draft.source_excerpts
    )


def _merge_compiled_answer_drafts(
    left: _CompiledAnswerEntryDraft,
    right: _CompiledAnswerEntryDraft,
) -> _CompiledAnswerEntryDraft:
    left_indices = left.metadata.get("preprocessing_entry_indices")
    right_indices = right.metadata.get("preprocessing_entry_indices")
    merged_indices: list[int] = []

    for value in (left_indices, right_indices):
        if not isinstance(value, tuple):
            continue
        for item in value:
            if isinstance(item, int) and item not in merged_indices:
                merged_indices.append(item)

    metadata: dict[str, object] = dict(left.metadata)
    metadata["compiler_merge"] = "exact_duplicate_grouping"
    metadata["preprocessing_entry_indices"] = tuple(merged_indices)
    metadata["merged_preprocessing_entry_count"] = len(merged_indices)

    return _CompiledAnswerEntryDraft(
        title=left.title,
        answer=_merge_answer_text(left.answer, right.answer),
        source_excerpts=_merge_text_tuple_values(
            left.source_excerpts,
            right.source_excerpts,
        ),
        source_refs=_merge_compiled_source_refs(
            left.source_refs,
            right.source_refs,
        ),
        questions=_merge_text_tuple_values(left.questions, right.questions),
        synonyms=_merge_text_tuple_values(left.synonyms, right.synonyms),
        tags=_merge_text_tuple_values(left.tags, right.tags),
        embedding_text=_merge_answer_text(left.embedding_text, right.embedding_text),
        metadata=metadata,
    )


def _compiled_answer_drafts_from_preprocessing_result(
    result: KnowledgePreprocessingResult,
) -> tuple[_CompiledAnswerEntryDraft, ...]:
    grouped: dict[str, _CompiledAnswerEntryDraft] = {}
    ordered_keys: list[str] = []

    for index, entry in enumerate(result.entries):
        draft = _preprocessing_entry_to_compiled_draft(
            entry,
            mode=result.mode,
            index=index,
        )
        if not draft.answer:
            continue

        key = _answer_topic_key(entry, index=index)
        if key in grouped:
            grouped[key] = _merge_compiled_answer_drafts(grouped[key], draft)
            continue

        grouped[key] = draft
        ordered_keys.append(key)

    return tuple(grouped[key] for key in ordered_keys)


KCD_STAGE_K8_ANSWER_RESOLUTION_MAX_GROUPS = 24
KCD_STAGE_K8_ANSWER_RESOLUTION_MAX_GROUP_SIZE = 2
KCD_STAGE_K8_ANSWER_RESOLUTION_CANDIDATE_ANSWER_MAX_CHARS = 900
KCD_STAGE_K8_ANSWER_RESOLUTION_MIN_TOKEN_CHARS = 3
KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT = 3


def _json_metric_int(metrics: Mapping[str, JsonValue], key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


@dataclass(frozen=True, slots=True)
class _MechanicalCleanupCompiledEntriesResult:
    entries: tuple[KnowledgePreprocessingEntry, ...]
    source_excerpts_by_entry: tuple[tuple[str, ...], ...]
    metrics: JsonObject


def _mechanically_cleanup_compiled_entries(
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
    source_excerpts_by_entry: Sequence[tuple[str, ...]],
) -> _MechanicalCleanupCompiledEntriesResult:
    source_excerpts = tuple(source_excerpts_by_entry)
    if len(source_excerpts) != len(entries):
        source_excerpts = tuple(
            _source_excerpts_from_preprocessing_entry(entry) for entry in entries
        )

    deduped_question_variant_count = 0
    deduped_synonym_count = 0
    deduped_tag_count = 0
    cleaned_entries: list[KnowledgePreprocessingEntry] = []
    cleaned_source_excerpts: list[tuple[str, ...]] = []

    for entry, entry_source_excerpts in zip(entries, source_excerpts, strict=True):
        deduped_entry, field_metrics = _retighten_entry_with_deduped_fields(entry)
        deduped_question_variant_count += _json_metric_int(
            field_metrics, "deduped_question_variant_count"
        )
        deduped_synonym_count += _json_metric_int(
            field_metrics, "deduped_synonym_count"
        )
        deduped_tag_count += _json_metric_int(field_metrics, "deduped_tag_count")
        cleaned_entries.append(deduped_entry)
        cleaned_source_excerpts.append(entry_source_excerpts)

    retained_entries: list[KnowledgePreprocessingEntry] = []
    retained_source_excerpts: list[tuple[str, ...]] = []
    retained_merged_entry_counts: list[int] = []
    index_by_exact_key: dict[tuple[str, str, str, str], int] = {}
    exact_duplicate_candidate_collapse_count = 0

    for entry, entry_source_excerpts in zip(
        cleaned_entries, cleaned_source_excerpts, strict=True
    ):
        source_fingerprint = " | ".join(
            _answer_resolution_text_fingerprint(excerpt)
            for excerpt in entry_source_excerpts
            if _answer_resolution_text_fingerprint(excerpt)
        )
        exact_key = (
            _answer_resolution_text_fingerprint(entry.title),
            _answer_resolution_text_fingerprint(entry.canonical_question),
            _answer_resolution_text_fingerprint(entry.answer),
            source_fingerprint,
        )
        existing_index = index_by_exact_key.get(exact_key)
        deterministic_reason = (
            "exact_candidate_key" if existing_index is not None else ""
        )

        if existing_index is None:
            for candidate_index, existing_entry in enumerate(retained_entries):
                reason = _retighten_deterministic_duplicate_reason(
                    existing_entry,
                    entry,
                )
                if reason is None:
                    continue
                existing_index = candidate_index
                deterministic_reason = reason
                break

        if existing_index is None:
            index_by_exact_key[exact_key] = len(retained_entries)
            retained_entries.append(entry)
            retained_source_excerpts.append(entry_source_excerpts)
            retained_merged_entry_counts.append(1)
            continue

        existing_entry = retained_entries[existing_index]
        if deterministic_reason == "exact_candidate_key":
            merged_entry = _merge_entry_fields_deterministically(
                existing_entry=existing_entry,
                incoming_entry=entry,
                merged_answer=existing_entry.answer,
            )
            exact_duplicate_candidate_collapse_count += 1
        else:
            merged_entry = _retighten_merge_entries_deterministically(
                existing_entry=existing_entry,
                incoming_entry=entry,
                reason=deterministic_reason,
            )

        retained_entries[existing_index] = merged_entry
        retained_source_excerpts[existing_index] = _merge_text_tuple_values(
            retained_source_excerpts[existing_index],
            entry_source_excerpts,
        )
        retained_merged_entry_counts[existing_index] += 1

    metrics: JsonObject = {
        "deduped_question_variant_count": deduped_question_variant_count,
        "deduped_synonym_count": deduped_synonym_count,
        "deduped_tag_count": deduped_tag_count,
        "exact_duplicate_candidate_collapse_count": (
            exact_duplicate_candidate_collapse_count
        ),
        "deterministic_candidate_collapse_count": (
            len(entries) - len(retained_entries)
        ),
        "deterministic_cleanup_entry_count_before": len(entries),
        "deterministic_cleanup_entry_count_after": len(retained_entries),
        "merged_preprocessing_entry_counts": cast(
            JsonValue, retained_merged_entry_counts
        ),
    }
    return _MechanicalCleanupCompiledEntriesResult(
        entries=tuple(retained_entries),
        source_excerpts_by_entry=tuple(retained_source_excerpts),
        metrics=metrics,
    )


def _entry_question_intent_fingerprints(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    values: list[str] = []
    for value in (
        entry.canonical_question,
        _question_intent_primary_question(entry),
        *_text_tuple(entry.questions),
    ):
        fingerprint = _answer_resolution_text_fingerprint(value)
        if fingerprint and fingerprint not in values:
            values.append(fingerprint)
    return tuple(values)


def _entries_have_exact_question_intent(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> bool:
    left_fingerprints = set(_entry_question_intent_fingerprints(left))
    right_fingerprints = set(_entry_question_intent_fingerprints(right))
    return bool(
        left_fingerprints
        and right_fingerprints
        and left_fingerprints & right_fingerprints
    )


KCD_STAGE_K8_REJECT_MERGE_REMOVED_UNIT_RATIO = 0.55


async def _existing_project_titles_for_answer_resolution(
    *,
    repo: KnowledgeIngestionRepositoryPort,
    project_id: str,
    document_id: str,
) -> tuple[str, ...]:
    try:
        titles = await repo.list_runtime_entry_titles(
            project_id=project_id,
            exclude_document_id=document_id,
            limit=300,
        )
    except (AttributeError, TypeError):
        return ()

    result: list[str] = []
    for title in titles:
        cleaned = _clean_optional_text(title)
        if cleaned and cleaned not in result:
            result.append(cleaned)

    return tuple(result)


KCD_STAGE_K_MERGED_QUESTION_LIMIT = 40
KCD_STAGE_K_MERGED_SYNONYM_LIMIT = 64
KCD_STAGE_K_MERGED_TAG_LIMIT = 32
KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS = 3600
KCD_STAGE_K_MERGED_SOURCE_EXCERPT_MAX_CHARS = 7000
KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS = 2400


@dataclass(frozen=True, slots=True)
class _RetightenExistingDocumentPlan:
    entries: tuple[KnowledgePreprocessingEntry, ...]
    survivor_source_indexes: tuple[int, ...]
    merged_source_indexes_by_entry: tuple[tuple[int, ...], ...]
    removed_source_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _DeterministicRetightenResult:
    plan: _RetightenExistingDocumentPlan
    metrics: JsonObject


def _retighten_deduped_text_tuple(
    values: object,
) -> tuple[tuple[str, ...], int]:
    result: list[str] = []
    seen: set[str] = set()
    duplicate_count = 0

    for value in _text_tuple(values):
        cleaned = _clean_optional_text(value)
        if not cleaned:
            continue

        fingerprint = _answer_resolution_text_fingerprint(cleaned)
        if not fingerprint:
            continue

        if fingerprint in seen:
            duplicate_count += 1
            continue

        seen.add(fingerprint)
        result.append(cleaned)

    return tuple(result), duplicate_count


def _retighten_entry_with_deduped_fields(
    entry: KnowledgePreprocessingEntry,
) -> tuple[KnowledgePreprocessingEntry, JsonObject]:
    questions, duplicate_question_count = _retighten_deduped_text_tuple(entry.questions)
    synonyms, duplicate_synonym_count = _retighten_deduped_text_tuple(entry.synonyms)
    tags, duplicate_tag_count = _retighten_deduped_text_tuple(entry.tags)

    answer_cleanup = _cleanup_answer_resolution_text_with_metrics(entry.answer)
    embedding_cleanup = _cleanup_answer_resolution_text_with_metrics(
        entry.embedding_text
    )

    deduped = KnowledgePreprocessingEntry(
        title=entry.title,
        answer=answer_cleanup.text or entry.answer,
        source_excerpt=entry.source_excerpt,
        questions=questions,
        synonyms=synonyms,
        tags=tags,
        embedding_text=embedding_cleanup.text or entry.embedding_text,
        canonical_question=entry.canonical_question,
    )
    metrics: JsonObject = {
        "deduped_question_variant_count": duplicate_question_count,
        "deduped_synonym_count": duplicate_synonym_count,
        "deduped_tag_count": duplicate_tag_count,
        "deduped_answer_unit_count": answer_cleanup.removed_unit_count,
        "deduped_embedding_text_unit_count": embedding_cleanup.removed_unit_count,
    }
    return deduped, metrics


def _retighten_entry_intent_fingerprint(
    entry: KnowledgePreprocessingEntry,
) -> str:
    return _answer_resolution_text_fingerprint(
        " ".join(
            part
            for part in (
                entry.title,
                entry.canonical_question,
                " ".join(_text_tuple(entry.questions)),
                " ".join(_text_tuple(entry.synonyms)),
            )
            if _clean_optional_text(part)
        )
    )


def _retighten_answer_fingerprint(entry: KnowledgePreprocessingEntry) -> str:
    return _answer_resolution_text_fingerprint(entry.answer)


def _retighten_answer_contains(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> bool:
    left_answer = _retighten_answer_fingerprint(left)
    right_answer = _retighten_answer_fingerprint(right)
    if not left_answer or not right_answer:
        return False
    if len(left_answer) < 32 or len(right_answer) < 32:
        return False
    return left_answer in right_answer or right_answer in left_answer


def _retighten_deterministic_duplicate_reason(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> str | None:
    left_answer = _retighten_answer_fingerprint(left)
    right_answer = _retighten_answer_fingerprint(right)
    if left_answer and right_answer and left_answer == right_answer:
        return "exact_answer"

    if _retighten_answer_contains(left, right):
        return "answer_containment"

    left_intent = _retighten_entry_intent_fingerprint(left)
    right_intent = _retighten_entry_intent_fingerprint(right)
    if _entries_have_exact_question_intent(left, right):
        answer_unit_merge = _merge_answer_units_deterministically(
            left.answer,
            right.answer,
            allow_disjoint_union=True,
        )
        if answer_unit_merge is not None:
            return answer_unit_merge.strategy

    if left_intent and right_intent and left_intent == right_intent:
        answer_score = _answer_resolution_token_similarity(
            _answer_resolution_tokens_from_text(left.answer),
            _answer_resolution_tokens_from_text(right.answer),
        )
        if answer_score >= 0.72:
            return "exact_intent_high_answer_overlap"

    return None


def _retighten_entry_richness_score(
    entry: KnowledgePreprocessingEntry,
) -> tuple[int, int, int, int]:
    return (
        len(_clean_optional_text(entry.answer)),
        len(_source_excerpts_from_preprocessing_entry(entry)),
        len(_text_tuple(entry.questions)),
        len(_clean_optional_text(entry.embedding_text)),
    )


def _retighten_merge_entries_deterministically(
    *,
    existing_entry: KnowledgePreprocessingEntry,
    incoming_entry: KnowledgePreprocessingEntry,
    reason: str,
) -> KnowledgePreprocessingEntry:
    existing_score = _retighten_entry_richness_score(existing_entry)
    incoming_score = _retighten_entry_richness_score(incoming_entry)
    survivor = incoming_entry if incoming_score > existing_score else existing_entry
    absorbed = existing_entry if survivor is incoming_entry else incoming_entry

    answer_unit_merge = _merge_answer_units_deterministically(
        existing_entry.answer,
        incoming_entry.answer,
        allow_disjoint_union=reason == "same_intent_complementary_answer_unit_union",
    )
    if answer_unit_merge is not None:
        survivor_answer = answer_unit_merge.answer
    elif reason == "answer_containment":
        survivor_answer = survivor.answer
    elif _retighten_answer_fingerprint(existing_entry) == _retighten_answer_fingerprint(
        incoming_entry
    ):
        survivor_answer = survivor.answer
    else:
        survivor_answer = _merge_answer_text(
            existing_entry.answer, incoming_entry.answer
        )

    merged = _merge_entry_fields_deterministically(
        existing_entry=survivor,
        incoming_entry=absorbed,
        merged_answer=survivor_answer,
    )
    deduped, _ = _retighten_entry_with_deduped_fields(merged)
    return deduped


def _retighten_entry_is_suspicious_meta(
    entry: KnowledgePreprocessingEntry,
) -> bool:
    """KAD v1 forbids keyword dictionaries for semantic/meta filtering.

    Deterministic code may dedupe and validate structure, but it must not
    classify meta/test/RAG/business roles by hardcoded terms.
    """
    return False


def _deterministic_retighten_existing_document_plan(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> _DeterministicRetightenResult:
    working_entries: list[KnowledgePreprocessingEntry] = []
    survivor_source_indexes: list[int] = []
    merged_source_indexes: list[list[int]] = []

    metrics: JsonObject = {
        "deterministic_duplicate_group_count": 0,
        "deterministic_collapsed_entry_count": 0,
        "deterministic_exact_answer_collapse_count": 0,
        "deterministic_exact_intent_merge_count": 0,
        "deterministic_answer_containment_merge_count": 0,
        "deterministic_answer_unit_subset_merge_count": 0,
        "deterministic_answer_unit_overlap_merge_count": 0,
        "deterministic_same_intent_complementary_merge_count": 0,
        "deduped_question_variant_count": 0,
        "deduped_synonym_count": 0,
        "deduped_tag_count": 0,
        "deduped_answer_unit_count": 0,
        "deduped_embedding_text_unit_count": 0,
        "suspicious_meta_entry_count": 0,
    }
    suspicious_examples: list[JsonObject] = []

    for source_index, raw_entry in enumerate(entries):
        entry, dedupe_metrics = _retighten_entry_with_deduped_fields(raw_entry)
        for key, value in dedupe_metrics.items():
            metrics[key] = int(cast(int, metrics.get(key, 0))) + int(cast(int, value))

        if _retighten_entry_is_suspicious_meta(entry):
            metrics["suspicious_meta_entry_count"] = (
                int(cast(int, metrics["suspicious_meta_entry_count"])) + 1
            )
            if len(suspicious_examples) < 5:
                suspicious_examples.append(
                    {
                        "title": _limit_compiled_text(entry.title, max_chars=120),
                        "answer_preview": _limit_compiled_text(
                            entry.answer,
                            max_chars=180,
                        ),
                    }
                )

        target_index: int | None = None
        target_reason: str | None = None
        for existing_index, existing_entry in enumerate(working_entries):
            reason = _retighten_deterministic_duplicate_reason(existing_entry, entry)
            if reason is None:
                continue
            target_index = existing_index
            target_reason = reason
            break

        if target_index is None or target_reason is None:
            working_entries.append(entry)
            survivor_source_indexes.append(source_index)
            merged_source_indexes.append([source_index])
            continue

        existing_entry = working_entries[target_index]
        existing_survivor = survivor_source_indexes[target_index]
        merged_entry = _retighten_merge_entries_deterministically(
            existing_entry=existing_entry,
            incoming_entry=entry,
            reason=target_reason,
        )

        if _retighten_entry_richness_score(entry) > _retighten_entry_richness_score(
            existing_entry
        ):
            survivor_source_indexes[target_index] = source_index
            if existing_survivor not in merged_source_indexes[target_index]:
                merged_source_indexes[target_index].append(existing_survivor)

        if source_index not in merged_source_indexes[target_index]:
            merged_source_indexes[target_index].append(source_index)

        working_entries[target_index] = merged_entry
        metrics["deterministic_duplicate_group_count"] = (
            int(cast(int, metrics["deterministic_duplicate_group_count"])) + 1
        )
        metrics["deterministic_collapsed_entry_count"] = (
            int(cast(int, metrics["deterministic_collapsed_entry_count"])) + 1
        )

        if target_reason == "exact_answer":
            metrics["deterministic_exact_answer_collapse_count"] = (
                int(cast(int, metrics["deterministic_exact_answer_collapse_count"])) + 1
            )
        elif target_reason == "answer_containment":
            metrics["deterministic_answer_containment_merge_count"] = (
                int(cast(int, metrics["deterministic_answer_containment_merge_count"]))
                + 1
            )
        elif target_reason == "exact_intent_high_answer_overlap":
            metrics["deterministic_exact_intent_merge_count"] = (
                int(cast(int, metrics["deterministic_exact_intent_merge_count"])) + 1
            )
        elif target_reason == "answer_unit_subset_superset":
            metrics["deterministic_answer_unit_subset_merge_count"] = (
                int(cast(int, metrics["deterministic_answer_unit_subset_merge_count"]))
                + 1
            )
        elif target_reason == "answer_unit_overlap_union":
            metrics["deterministic_answer_unit_overlap_merge_count"] = (
                int(cast(int, metrics["deterministic_answer_unit_overlap_merge_count"]))
                + 1
            )
        elif target_reason == "same_intent_complementary_answer_unit_union":
            metrics["deterministic_same_intent_complementary_merge_count"] = (
                int(
                    cast(
                        int,
                        metrics["deterministic_same_intent_complementary_merge_count"],
                    )
                )
                + 1
            )

    survivor_set = set(survivor_source_indexes)
    removed_source_indexes = tuple(
        sorted(
            source_index
            for source_indexes in merged_source_indexes
            for source_index in source_indexes
            if source_index not in survivor_set
        )
    )
    if suspicious_examples:
        metrics["suspicious_meta_examples"] = cast(JsonValue, suspicious_examples)

    return _DeterministicRetightenResult(
        plan=_RetightenExistingDocumentPlan(
            entries=tuple(working_entries),
            survivor_source_indexes=tuple(survivor_source_indexes),
            merged_source_indexes_by_entry=tuple(
                tuple(source_indexes) for source_indexes in merged_source_indexes
            ),
            removed_source_indexes=removed_source_indexes,
        ),
        metrics=metrics,
    )


def _compose_retighten_existing_document_plans(
    *,
    base: _RetightenExistingDocumentPlan,
    overlay: _RetightenExistingDocumentPlan,
) -> _RetightenExistingDocumentPlan:
    survivor_source_indexes = tuple(
        base.survivor_source_indexes[index] for index in overlay.survivor_source_indexes
    )

    merged_source_indexes_by_entry: list[tuple[int, ...]] = []
    for overlay_source_indexes in overlay.merged_source_indexes_by_entry:
        original_indexes: list[int] = []
        for base_index in overlay_source_indexes:
            if base_index < 0 or base_index >= len(base.merged_source_indexes_by_entry):
                continue
            for original_index in base.merged_source_indexes_by_entry[base_index]:
                if original_index not in original_indexes:
                    original_indexes.append(original_index)
        merged_source_indexes_by_entry.append(tuple(original_indexes))

    removed_source_indexes: set[int] = set(base.removed_source_indexes)
    for base_index in overlay.removed_source_indexes:
        if base_index < 0 or base_index >= len(base.merged_source_indexes_by_entry):
            continue
        removed_source_indexes.update(base.merged_source_indexes_by_entry[base_index])

    survivor_set = set(survivor_source_indexes)
    removed_source_indexes = {
        source_index
        for source_index in removed_source_indexes
        if source_index not in survivor_set
    }

    return _RetightenExistingDocumentPlan(
        entries=overlay.entries,
        survivor_source_indexes=survivor_source_indexes,
        merged_source_indexes_by_entry=tuple(merged_source_indexes_by_entry),
        removed_source_indexes=tuple(sorted(removed_source_indexes)),
    )


def _preprocessing_entry_from_canonical_entry(
    entry: CanonicalKnowledgeEntry,
) -> KnowledgePreprocessingEntry:
    source_excerpt = "\n\n".join(
        source_ref.quote for source_ref in entry.source_refs if source_ref.quote
    )
    embedding_text = entry.embedding_text.value if entry.embedding_text else ""
    return KnowledgePreprocessingEntry(
        title=entry.title,
        answer=entry.answer,
        source_excerpt=source_excerpt,
        questions=entry.enrichment.questions,
        synonyms=entry.enrichment.synonyms,
        tags=entry.enrichment.tags,
        embedding_text=_clean_optional_text(embedding_text) or entry.answer,
    )


def _retighten_existing_document_plan(
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
    decisions: Sequence[KnowledgeAnswerResolutionDecision],
) -> _RetightenExistingDocumentPlan:
    updated_entries: list[KnowledgePreprocessingEntry] = list(entries)
    merged_source_indexes: list[list[int]] = [[index] for index in range(len(entries))]
    removed_indexes: set[int] = set()

    for decision in decisions:
        if not decision.is_merge:
            continue

        candidate_indexes: list[int] = []
        for candidate_id in decision.candidate_ids:
            index = _answer_resolution_candidate_index(candidate_id)
            if index is None or index < 0 or index >= len(entries):
                continue
            if index in candidate_indexes or index in removed_indexes:
                continue
            candidate_indexes.append(index)

        if len(candidate_indexes) < 2:
            continue

        ordered_indexes = tuple(sorted(candidate_indexes))
        survivor_index = _answer_resolution_survivor_index(
            decision=decision,
            candidate_indexes=ordered_indexes,
            entries=entries,
        )

        merged_entry = updated_entries[survivor_index]
        for index in ordered_indexes:
            if index == survivor_index:
                continue
            merged_entry = _merge_entry_fields_deterministically(
                existing_entry=merged_entry,
                incoming_entry=updated_entries[index],
                merged_answer=decision.canonical_answer,
            )

        merged_indexes_for_survivor: list[int] = []
        for index in ordered_indexes:
            for source_index in merged_source_indexes[index]:
                if source_index not in merged_indexes_for_survivor:
                    merged_indexes_for_survivor.append(source_index)

        updated_entries[survivor_index] = _entry_with_answer_resolution_decision(
            entry=merged_entry,
            decision=decision,
        )
        merged_source_indexes[survivor_index] = merged_indexes_for_survivor
        removed_indexes.update(
            index for index in ordered_indexes if index != survivor_index
        )

    survivor_indexes = tuple(
        index for index in range(len(updated_entries)) if index not in removed_indexes
    )
    return _RetightenExistingDocumentPlan(
        entries=tuple(updated_entries[index] for index in survivor_indexes),
        survivor_source_indexes=survivor_indexes,
        merged_source_indexes_by_entry=tuple(
            tuple(merged_source_indexes[index]) for index in survivor_indexes
        ),
        removed_source_indexes=tuple(sorted(removed_indexes)),
    )


def _merge_source_refs_for_existing_entry_indexes(
    *,
    source_indexes: Sequence[int],
    entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[SourceRef, ...]:
    refs: tuple[SourceRef, ...] = ()
    for index in source_indexes:
        if index < 0 or index >= len(entries):
            continue
        refs = _merge_compiled_source_refs(refs, entries[index].source_refs)
    return refs


def _retightened_canonical_entry(
    *,
    original: CanonicalKnowledgeEntry,
    entry: KnowledgePreprocessingEntry,
    source_refs: tuple[SourceRef, ...],
    merged_from_entry_ids: Sequence[str],
) -> CanonicalKnowledgeEntry:
    metadata: dict[str, object] = dict(original.metadata)
    metadata["answer_resolution"] = {
        "strategy": "kcd_stage_k8_existing_document_retighten",
        "merged_from_entry_ids": tuple(merged_from_entry_ids),
        "merged_source_entry_count": len(merged_from_entry_ids),
    }

    embedding_text = (
        _clean_optional_text(entry.embedding_text)
        or (original.embedding_text.value if original.embedding_text else "")
        or entry.answer
    )

    return CanonicalKnowledgeEntry(
        id=original.id,
        project_id=original.project_id,
        document_id=original.document_id,
        compiler_run_id=original.compiler_run_id,
        stable_key=original.stable_key,
        entry_kind=original.entry_kind,
        title=entry.title,
        answer=entry.answer,
        source_refs=source_refs,
        enrichment=KnowledgeEnrichment(
            questions=_text_tuple(entry.questions),
            synonyms=_text_tuple(entry.synonyms),
            tags=_text_tuple(entry.tags),
        ),
        embedding_text=EmbeddingText(
            value=embedding_text,
            version=CANONICAL_EMBEDDING_TEXT_VERSION,
        ),
        status=KnowledgeEntryStatus.PUBLISHED,
        visibility=KnowledgeEntryVisibility.RUNTIME,
        version=original.version + 1,
        compiler_version=original.compiler_version,
        embedding_text_version=CANONICAL_EMBEDDING_TEXT_VERSION,
        metadata=metadata,
    )


def _retighten_updated_canonical_entries(
    *,
    plan: _RetightenExistingDocumentPlan,
    current_entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    updated_entries: list[CanonicalKnowledgeEntry] = []
    for output_index, tightened_entry in enumerate(plan.entries):
        survivor_source_index = plan.survivor_source_indexes[output_index]
        merged_source_indexes = plan.merged_source_indexes_by_entry[output_index]
        original = current_entries[survivor_source_index]
        source_refs = _merge_source_refs_for_existing_entry_indexes(
            source_indexes=merged_source_indexes,
            entries=current_entries,
        )
        updated_entries.append(
            _retightened_canonical_entry(
                original=original,
                entry=tightened_entry,
                source_refs=source_refs,
                merged_from_entry_ids=tuple(
                    current_entries[index].id for index in merged_source_indexes
                ),
            )
        )
    return tuple(updated_entries)


def _retighten_archived_entry_ids(
    *,
    plan: _RetightenExistingDocumentPlan,
    current_entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[str, ...]:
    return tuple(
        current_entries[index].id
        for index in plan.removed_source_indexes
        if 0 <= index < len(current_entries)
    )


def _preprocessing_result_from_entries(
    *,
    mode: KnowledgePreprocessingMode,
    template: KnowledgePreprocessingResult,
    entries: Sequence[KnowledgePreprocessingEntry],
    metrics: JsonObject,
) -> KnowledgePreprocessingResult:
    return KnowledgePreprocessingResult(
        mode=mode,
        prompt_version=template.prompt_version,
        model=template.model,
        entries=tuple(entries),
        metrics=metrics,
    )


def _canonical_entries_from_knowledge_chunks(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    chunks: Sequence[KnowledgeChunk],
    source_chunks: Sequence[SourceChunk],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    entries: list[CanonicalKnowledgeEntry] = []

    for index, chunk in enumerate(chunks):
        source_chunk = _source_chunk_for_knowledge_chunk(
            chunk=chunk,
            index=index,
            source_chunks=source_chunks,
        )
        stable_key = _canonical_entry_stable_key(
            document_id=document_id,
            index=index,
            chunk=chunk,
        )
        entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))
        title = (
            chunk.title or chunk.section_path.title or f"Knowledge entry {index + 1}"
        )

        entries.append(
            CanonicalKnowledgeEntry(
                id=entry_id,
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                stable_key=stable_key,
                entry_kind=_entry_kind_from_chunk_role(chunk.role),
                title=title,
                answer=chunk.content,
                source_refs=(
                    _canonical_source_ref(chunk=chunk, source_chunk=source_chunk),
                ),
                enrichment=KnowledgeEnrichment(
                    questions=chunk.questions,
                    synonyms=chunk.synonyms,
                    tags=chunk.tags,
                ),
                embedding_text=None,
                status=KnowledgeEntryStatus.PUBLISHED,
                visibility=KnowledgeEntryVisibility.RUNTIME,
                version=1,
                compiler_version=KCD_STAGE_E_COMPILER_VERSION,
                embedding_text_version=CANONICAL_EMBEDDING_TEXT_VERSION,
                metadata=dict(chunk.metadata),
            )
        )

    return tuple(entries)


def _stage_e_compiler_run_id(
    *,
    document_id: str,
    mode: KnowledgePreprocessingMode,
) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"kcd_v1_stage_e:{document_id}:{mode}",
        )
    )


def _stage_e_compiler_run(
    *,
    project_id: str,
    document_id: str,
    mode: KnowledgePreprocessingMode,
    source_chunk_count: int,
) -> CompilerRun:
    return CompilerRun(
        id=_stage_e_compiler_run_id(document_id=document_id, mode=mode),
        project_id=project_id,
        document_id=document_id,
        mode=str(mode),
        compiler_version=KCD_STAGE_K_COMPILER_VERSION,
        status=CompilerRunStatus.RUNNING,
        metrics=CompilationMetrics(source_chunk_count=source_chunk_count),
    )


def _stage_e_answer_candidates_from_entries(
    entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[AnswerCandidate, ...]:
    candidates: list[AnswerCandidate] = []

    for entry in entries:
        candidate_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{entry.id}:candidate"))
        candidates.append(
            AnswerCandidate(
                id=candidate_id,
                document_id=entry.document_id,
                project_id=entry.project_id,
                compiler_run_id=entry.compiler_run_id,
                topic_key=entry.stable_key,
                title=entry.title,
                candidate_answer=entry.answer,
                source_refs=entry.source_refs,
                confidence=1.0 if entry.has_source_refs else None,
                status=AnswerCandidateStatus.MERGED,
                metadata={
                    "entry_id": entry.id,
                    "stable_key": entry.stable_key,
                    "entry_kind": entry.entry_kind.value,
                    "stage": (
                        "stage_k_answer_compiler"
                        if entry.compiler_version == KCD_STAGE_K_COMPILER_VERSION
                        else "stage_e_one_to_one_trace"
                    ),
                },
            )
        )

    return tuple(candidates)


def _stage_e_candidate_clusters_from_entries(
    *,
    entries: Sequence[CanonicalKnowledgeEntry],
    candidates: Sequence[AnswerCandidate],
) -> tuple[CandidateCluster, ...]:
    clusters: list[CandidateCluster] = []

    for entry, candidate in zip(entries, candidates, strict=True):
        clusters.append(
            CandidateCluster(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{entry.id}:cluster")),
                document_id=entry.document_id,
                project_id=entry.project_id,
                compiler_run_id=entry.compiler_run_id,
                cluster_key=entry.stable_key,
                topic=entry.title,
                candidate_ids=(candidate.id,),
                status=CandidateClusterStatus.CANONICAL_ENTRY_CREATED,
                merge_strategy="stage_e_one_to_one",
                merge_reason=(
                    "Initial Stage E trace keeps one candidate per canonical entry "
                    "until real clustering is introduced."
                ),
                metadata={
                    "entry_id": entry.id,
                    "stable_key": entry.stable_key,
                    "entry_kind": entry.entry_kind.value,
                },
            )
        )

    return tuple(clusters)


def _stage_e_compilation_metrics(
    *,
    source_chunks: Sequence[SourceChunk],
    entries: Sequence[CanonicalKnowledgeEntry],
    candidates: Sequence[AnswerCandidate],
    clusters: Sequence[CandidateCluster],
) -> CompilationMetrics:
    grounded_candidates = sum(1 for candidate in candidates if candidate.has_grounding)
    rejected_candidates = sum(
        1
        for candidate in candidates
        if candidate.status == AnswerCandidateStatus.REJECTED
    )
    published_entries = sum(1 for entry in entries if entry.is_published_runtime_entry)
    embedded_entries = len(entries)
    entries_without_source_refs = sum(
        1 for entry in entries if not entry.has_source_refs
    )

    return CompilationMetrics(
        source_chunk_count=len(source_chunks),
        answer_candidate_count=len(candidates),
        grounded_candidate_count=grounded_candidates,
        rejected_candidate_count=rejected_candidates,
        candidate_cluster_count=len(clusters),
        canonical_entry_count=len(entries),
        enriched_entry_count=len(entries),
        embedded_entry_count=embedded_entries,
        published_entry_count=published_entries,
        fallback_row_count=sum(
            1
            for entry in entries
            if entry.entry_kind == KnowledgeEntryKind.FALLBACK_CHUNK
        ),
        entries_without_source_refs_count=entries_without_source_refs,
    )


async def _persist_stage_e_compiler_outputs(
    *,
    repo: KnowledgeIngestionRepositoryPort,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    source_chunks: Sequence[SourceChunk],
    entries: Sequence[CanonicalKnowledgeEntry],
    complete_run: bool = True,
) -> None:
    candidates = _stage_e_answer_candidates_from_entries(entries)
    clusters = _stage_e_candidate_clusters_from_entries(
        entries=entries,
        candidates=candidates,
    )

    try:
        await repo.add_answer_candidates(
            project_id=project_id,
            document_id=document_id,
            candidates=candidates,
        )
        await repo.add_canonical_entries(
            project_id=project_id,
            document_id=document_id,
            entries=entries,
        )
        await repo.add_candidate_clusters(
            project_id=project_id,
            document_id=document_id,
            clusters=clusters,
        )
        if complete_run:
            await repo.complete_compiler_run(
                compiler_run_id,
                _stage_e_compilation_metrics(
                    source_chunks=source_chunks,
                    entries=entries,
                    candidates=candidates,
                    clusters=clusters,
                ),
            )
    except Exception as exc:
        await repo.fail_compiler_run(compiler_run_id, str(exc))
        raise


class KnowledgeIngestionService:
    def __init__(self, pool: KnowledgeDbPoolPort) -> None:
        self.pool = pool

    async def _persist_plain_chunks(
        self,
        *,
        repo: KnowledgeIngestionRepositoryPort,
        project_id: str,
        document_id: str,
        file_name: str,
        chunks: list[JsonObject],
        source_chunks: Sequence[SourceChunk],
        compiler_run_id: str,
        logger: LoggerPort,
        context: str,
    ) -> None:
        _log_plain_chunk_audit(
            logger,
            project_id=project_id,
            document_id=document_id,
            chunks=chunks,
            context=context,
        )
        document = _document_from_json_chunks(file_name=file_name, chunks=chunks)
        normalized = KnowledgeNormalizationService().normalize_document(
            document,
            project_id=project_id,
            document_id=document_id,
        )
        if not normalized.chunks:
            message = "No normalized knowledge chunks after filtering"
            await repo.update_document_status(document_id, "error", message)
            raise ValidationError(message)

        try:
            canonical_entries = _canonical_entries_from_knowledge_chunks(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                chunks=normalized.chunks,
                source_chunks=source_chunks,
            )
            await _persist_stage_e_compiler_outputs(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                source_chunks=source_chunks,
                entries=canonical_entries,
            )
        except EmbeddingProviderError as exc:
            if exc.retryable:
                logger.warning(
                    "Knowledge embedding provider temporary failure",
                    extra={
                        "project_id": project_id,
                        "document_id": document_id,
                        "provider": exc.provider,
                        "task": exc.task,
                        "model": exc.model,
                        "error_type": type(exc).__name__,
                        "context": context,
                    },
                )
                raise

            logger.warning(
                "Knowledge embedding provider permanent failure",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "provider": exc.provider,
                    "task": exc.task,
                    "model": exc.model,
                    "error_type": type(exc).__name__,
                    "context": context,
                },
            )
            await repo.update_document_status(document_id, "error", exc.detail)
            raise
        except KnowledgeDocumentDeletedDuringProcessingError as exc:
            logger.warning(
                "Knowledge document disappeared before plain chunks were persisted",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "context": context,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        except Exception as exc:
            logger.exception(
                "Knowledge plain chunk persistence failed",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "context": context,
                    "error_type": type(exc).__name__,
                },
            )
            await repo.update_document_status(document_id, "error", str(exc))
            raise

    async def retighten_processed_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        repo = knowledge_repo_factory(self.pool)
        usage_repo = model_usage_repo_factory(self.pool)
        current_entries = await repo.list_document_runtime_entries(
            project_id=project_id,
            document_id=document_id,
        )

        metrics: JsonObject = {
            "stage": "answer_resolution_existing_document",
            "source": "kcd_stage_k8_3",
            "entry_count_before": len(current_entries),
            "source_compiler_rerun": False,
        }

        if len(current_entries) < 2:
            metrics["status"] = "skipped"
            metrics["reason"] = "document_has_less_than_two_runtime_entries"
            metrics["entry_count_after"] = len(current_entries)
            return metrics

        preprocessing_entries = tuple(
            _preprocessing_entry_from_canonical_entry(entry)
            for entry in current_entries
        )

        deterministic_result = _deterministic_retighten_existing_document_plan(
            preprocessing_entries
        )
        deterministic_plan = deterministic_result.plan
        preprocessing_entries = deterministic_plan.entries
        metrics.update(deterministic_result.metrics)

        groups = _answer_resolution_cases_from_entries(preprocessing_entries)
        metrics["candidate_case_count"] = len(groups)
        metrics["llm_candidate_case_count"] = len(groups)

        if not groups:
            metrics["status"] = (
                "completed" if deterministic_plan.removed_source_indexes else "skipped"
            )
            metrics["reason"] = (
                "deterministic_cleanup_applied_without_llm_groups"
                if deterministic_plan.removed_source_indexes
                else "no_answer_resolution_cases"
            )
            metrics["entry_count_after"] = len(deterministic_plan.entries)
            metrics["collapsed_entry_count"] = len(
                deterministic_plan.removed_source_indexes
            )
            metrics["llm_call_count"] = 0
            metrics["usage_event_count"] = 0
            if not deterministic_plan.removed_source_indexes:
                return metrics

            result = await repo.apply_document_answer_resolution_retightening(
                project_id=project_id,
                document_id=document_id,
                updated_entries=_retighten_updated_canonical_entries(
                    plan=deterministic_plan,
                    current_entries=current_entries,
                ),
                archived_entry_ids=_retighten_archived_entry_ids(
                    plan=deterministic_plan,
                    current_entries=current_entries,
                ),
                metrics=metrics,
            )
            logger.info(
                "Knowledge document deterministic retighten completed",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "entry_count_before": len(current_entries),
                    "entry_count_after": len(deterministic_plan.entries),
                    "collapsed_entry_count": len(
                        deterministic_plan.removed_source_indexes
                    ),
                },
            )
            return result

        preprocessor = preprocessor_factory()
        existing_project_titles = await _existing_project_titles_for_answer_resolution(
            repo=repo,
            project_id=project_id,
            document_id=document_id,
        )
        llm_call_count = 0
        usage_event_count = 0
        try:
            first_execution = await preprocessor.resolve_answer_cases(
                mode=MODE_PRICE_LIST,
                file_name=file_name,
                cases=(groups[0],),
                existing_project_titles=existing_project_titles,
            )
            llm_call_count = 1
            decisions = _answer_resolution_decisions_with_case_candidate_ids(
                answer_case=groups[0],
                decisions=first_execution.result.decisions,
            )
            model = first_execution.result.model
            prompt_version = first_execution.result.prompt_version
            if first_execution.usage is not None:
                await usage_repo.record_event(
                    ModelUsageEventCreate.from_measurement(
                        project_id=project_id,
                        source="knowledge_preprocessing",
                        measurement=first_execution.usage,
                        document_id=document_id,
                    )
                )
                usage_event_count += 1

            for group in groups[1:]:
                execution = await preprocessor.resolve_answer_cases(
                    mode=MODE_PRICE_LIST,
                    file_name=file_name,
                    cases=(group,),
                    existing_project_titles=existing_project_titles,
                )
                llm_call_count += 1
                decisions = (
                    *decisions,
                    *_answer_resolution_decisions_with_case_candidate_ids(
                        answer_case=group,
                        decisions=execution.result.decisions,
                    ),
                )
                model = execution.result.model
                prompt_version = execution.result.prompt_version
                if execution.usage is not None:
                    await usage_repo.record_event(
                        ModelUsageEventCreate.from_measurement(
                            project_id=project_id,
                            source="knowledge_preprocessing",
                            measurement=execution.usage,
                            document_id=document_id,
                        )
                    )
                    usage_event_count += 1
        except Exception as exc:
            metrics["status"] = "skipped"
            metrics["reason"] = "answer_resolution_failed"
            metrics["error_type"] = type(exc).__name__
            metrics["error"] = str(exc)[:240]
            metrics["entry_count_after"] = len(current_entries)
            metrics["llm_call_count"] = llm_call_count
            metrics["usage_event_count"] = usage_event_count
            logger.warning(
                "Knowledge document answer resolution retighten skipped after LLM failure",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "candidate_case_count": len(groups),
                    "llm_call_count": llm_call_count,
                    "error_type": type(exc).__name__,
                },
            )
            if not deterministic_plan.removed_source_indexes:
                return metrics

            metrics["status"] = "completed_with_warnings"
            metrics["reason"] = "answer_resolution_failed_after_deterministic_cleanup"
            metrics["entry_count_after"] = len(deterministic_plan.entries)
            metrics["collapsed_entry_count"] = len(
                deterministic_plan.removed_source_indexes
            )
            result = await repo.apply_document_answer_resolution_retightening(
                project_id=project_id,
                document_id=document_id,
                updated_entries=_retighten_updated_canonical_entries(
                    plan=deterministic_plan,
                    current_entries=current_entries,
                ),
                archived_entry_ids=_retighten_archived_entry_ids(
                    plan=deterministic_plan,
                    current_entries=current_entries,
                ),
                metrics=metrics,
            )
            return result

        rejected_noisy_resolved_answer_count = sum(
            1
            for decision in decisions
            if _answer_resolution_decision_is_too_noisy(decision)
        )
        rejected_noisy_resolution_examples: tuple[JsonObject, ...] = tuple(
            cast(
                JsonObject,
                {
                    "group_id": decision.group_id,
                    "candidate_ids": tuple(decision.candidate_ids),
                    "canonical_answer_preview": _limit_compiled_text(
                        decision.canonical_answer,
                        max_chars=240,
                    ),
                    "cleanup_original_unit_count": (
                        cleanup := _cleanup_answer_resolution_text_with_metrics(
                            decision.canonical_answer
                        )
                    ).original_unit_count,
                    "cleanup_removed_unit_count": cleanup.removed_unit_count,
                },
            )
            for decision in decisions
            if _answer_resolution_decision_is_too_noisy(decision)
        )[:5]
        decisions = _reject_noisy_answer_resolution_decisions(decisions)

        llm_plan = _retighten_existing_document_plan(
            entries=preprocessing_entries,
            decisions=decisions,
        )
        plan = _compose_retighten_existing_document_plans(
            base=deterministic_plan,
            overlay=llm_plan,
        )

        cleanup_results = tuple(
            _cleanup_answer_resolution_text_with_metrics(decision.canonical_answer)
            for decision in decisions
            if decision.is_merge and decision.canonical_answer
        )
        metrics["retighten_cleanup_original_unit_count"] = sum(
            result.original_unit_count for result in cleanup_results
        )
        metrics["retighten_cleanup_removed_unit_count"] = sum(
            result.removed_unit_count for result in cleanup_results
        )
        metrics["rejected_noisy_resolved_answer_count"] = (
            rejected_noisy_resolved_answer_count
        )
        if rejected_noisy_resolution_examples:
            metrics["rejected_noisy_resolution_examples"] = list(
                rejected_noisy_resolution_examples
            )
        metrics["decision_count"] = len(decisions)
        metrics["resolved_answer_count"] = sum(
            1 for decision in decisions if decision.is_merge
        )
        metrics["collapsed_entry_count"] = len(plan.removed_source_indexes)
        metrics["deterministic_entry_count_after"] = len(deterministic_plan.entries)
        metrics["llm_resolved_entry_count"] = max(
            0,
            len(deterministic_plan.entries) - len(plan.entries),
        )
        metrics["entry_count_after"] = len(plan.entries)
        metrics["llm_call_count"] = llm_call_count
        metrics["usage_event_count"] = usage_event_count
        metrics["model"] = model
        metrics["prompt_version"] = prompt_version

        if not plan.removed_source_indexes:
            metrics["status"] = "completed"
            metrics["reason"] = "llm_kept_suspects_separate"
            return metrics

        result = await repo.apply_document_answer_resolution_retightening(
            project_id=project_id,
            document_id=document_id,
            updated_entries=_retighten_updated_canonical_entries(
                plan=plan,
                current_entries=current_entries,
            ),
            archived_entry_ids=_retighten_archived_entry_ids(
                plan=plan,
                current_entries=current_entries,
            ),
            metrics=metrics,
        )

        logger.info(
            "Knowledge document answer resolution retighten completed",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "entry_count_before": len(current_entries),
                "entry_count_after": len(plan.entries),
                "collapsed_entry_count": len(plan.removed_source_indexes),
            },
        )
        return result

    async def publish_ready_answers(
        self,
        *,
        project_id: str,
        document_id: str,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        repo = knowledge_repo_factory(self.pool)
        document = await repo.get_document(document_id)
        if document is None or document.project_id != project_id:
            raise ValidationError("Knowledge document not found")

        mode = normalize_preprocessing_mode(document.preprocessing_mode)
        if mode == MODE_FAQ:
            raise KnowledgePreprocessingValidationError(
                "Legacy knowledge ingestion preprocessor path is forbidden for mode=faq. "
                "Use Retrieval Surface Compilation pipeline."
            )
        if document.status in {"pending", "processing"} or (
            document.preprocessing_status == PREPROCESSING_STATUS_PROCESSING
        ):
            raise ValidationError(
                "Knowledge document is still processing; wait before publishing drafts"
            )

        source_chunks = await repo.list_document_source_chunks(
            project_id=project_id,
            document_id=document_id,
        )
        if not source_chunks:
            raise ValidationError("Knowledge document has no saved source chunks")

        runtime_entries = await repo.list_document_runtime_entries(
            project_id=project_id,
            document_id=document_id,
        )

        raw_candidates = await repo.list_document_raw_answer_candidates(
            project_id=project_id,
            document_id=document_id,
        )
        if not raw_candidates and not runtime_entries:
            raise ValidationError("Knowledge document has no ready answer drafts")

        batches = await repo.list_document_compiler_batches(
            project_id=project_id,
            document_id=document_id,
        )
        batch_failed = sum(1 for batch in batches if batch.status == "failed")
        batch_completed = sum(1 for batch in batches if batch.status == "completed")
        all_batches_completed = bool(batches) and all(
            batch.status == "completed" for batch in batches
        )
        compiler_run_id = (
            runtime_entries[0].compiler_run_id
            if runtime_entries
            else raw_candidates[0].compiler_run_id
        )

        canonical_entries = (
            runtime_entries
            if runtime_entries
            else _canonical_entries_from_raw_answer_candidates(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                mode=mode,
                candidates=raw_candidates,
            )
        )
        if not canonical_entries:
            raise ValidationError("Knowledge document has no publishable answer drafts")

        await _persist_stage_e_compiler_outputs(
            repo=repo,
            project_id=project_id,
            document_id=document_id,
            compiler_run_id=compiler_run_id,
            source_chunks=source_chunks,
            entries=canonical_entries,
            complete_run=all_batches_completed,
        )

        metrics: JsonObject = {
            "stage": "publish_ready",
            "status_message": (
                "Готовые ответы опубликованы; проблемные части можно повторить"
                if batch_failed > 0
                else "Готовые ответы опубликованы в базу знаний"
            ),
            "raw_answer_count": len(raw_candidates),
            "published_answer_count": len(canonical_entries),
            "canonical_entry_count": len(canonical_entries),
            "batch_completed": batch_completed,
            "batch_failed": batch_failed,
            "partial_publish": batch_failed > 0,
        }
        await repo.update_document_preprocessing_status(
            document_id,
            mode=mode,
            status=PREPROCESSING_STATUS_COMPLETED,
            model=document.preprocessing_model,
            prompt_version=document.preprocessing_prompt_version,
            metrics=metrics,
        )
        await repo.update_document_status(document_id, "processed")

        logger.info(
            "Knowledge ready answer drafts published",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "published_answer_count": len(canonical_entries),
                "batch_failed": batch_failed,
            },
        )
        return {
            "status": "completed" if batch_failed == 0 else "partial",
            "document_id": document_id,
            "published_answer_count": len(canonical_entries),
            "raw_answer_count": len(raw_candidates),
            "remaining_failed_batch_count": batch_failed,
        }

    async def retry_failed_batches(
        self,
        *,
        project_id: str,
        document_id: str,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        repo = knowledge_repo_factory(self.pool)
        usage_repo = model_usage_repo_factory(self.pool)
        document = await repo.get_document(document_id)
        if document is None or document.project_id != project_id:
            raise ValidationError("Knowledge document not found")

        mode = normalize_preprocessing_mode(document.preprocessing_mode)
        if mode == MODE_FAQ:
            raise KnowledgePreprocessingValidationError(
                "Legacy knowledge ingestion retry path is forbidden for mode=faq. "
                "Use Retrieval Surface Compilation pipeline."
            )

        source_chunks = await repo.list_document_source_chunks(
            project_id=project_id,
            document_id=document_id,
        )
        if not source_chunks:
            raise ValidationError("Knowledge document has no saved source chunks")

        batches = await repo.list_document_compiler_batches(
            project_id=project_id,
            document_id=document_id,
        )
        failed_batches = tuple(batch for batch in batches if batch.status == "failed")
        if not failed_batches:
            return {
                "status": "skipped",
                "reason": "no_failed_batches",
                "document_id": document_id,
            }

        source_json_chunks = _json_chunks_from_source_chunks(source_chunks)
        technical_batches = tuple(
            _technical_chunk_batches_for_answer_compiler(source_json_chunks)
        )
        preprocessor = preprocessor_factory()
        await repo.update_document_preprocessing_status(
            document_id,
            mode=mode,
            status=PREPROCESSING_STATUS_PROCESSING,
            model=preprocessor.model_name,
            prompt_version=prompt_version_for_mode(mode),
            metrics={
                "stage": "retry_failed_batches",
                "failed_batch_count_before": len(failed_batches),
            },
        )
        await repo.update_document_status(document_id, "processing")
        usage_event_count = 0
        retried_batch_count = 0

        for batch in failed_batches:
            if batch.batch_index < 1 or batch.batch_index > len(technical_batches):
                await repo.fail_compiler_batch(
                    batch.id,
                    error_type="ValidationError",
                    error_message="Saved compiler batch index is outside reconstructed technical batch range",
                )
                continue

            technical_chunks = technical_batches[batch.batch_index - 1]
            await repo.mark_compiler_batch_processing(
                batch.id,
                attempt_count=batch.attempt_count + 1,
            )
            try:
                execution = await preprocessor.preprocess(
                    mode=mode,
                    chunks=technical_chunks,
                    file_name=document.file_name,
                )
                if execution.usage is not None:
                    await usage_repo.record_event(
                        ModelUsageEventCreate.from_measurement(
                            project_id=project_id,
                            source="knowledge_preprocessing",
                            measurement=execution.usage,
                            document_id=document_id,
                        )
                    )
                    usage_event_count += 1

                safe_entries = tuple(execution.result.entries)
                raw_candidates = _raw_answer_candidates_from_preprocessing_entries(
                    project_id=project_id,
                    document_id=document_id,
                    compiler_run_id=batch.compiler_run_id,
                    batch_id=batch.id,
                    batch_index=batch.batch_index,
                    entries=safe_entries,
                    source_chunks=source_chunks,
                    mode=mode,
                )
                await repo.delete_raw_answer_candidates_for_batch(
                    project_id=project_id,
                    document_id=document_id,
                    batch_id=batch.id,
                )
                await repo.add_answer_candidates(
                    project_id=project_id,
                    document_id=document_id,
                    candidates=raw_candidates,
                )
                usage = execution.usage
                await repo.complete_compiler_batch(
                    batch.id,
                    model=execution.result.model,
                    prompt_version=execution.result.prompt_version,
                    tokens_input=usage.tokens_input if usage is not None else 0,
                    tokens_output=usage.tokens_output
                    if usage is not None and usage.tokens_output is not None
                    else 0,
                    tokens_total=usage.tokens_total if usage is not None else 0,
                )
                retried_batch_count += 1
            except Exception as exc:
                error_message = str(exc)[:500] or type(exc).__name__
                await repo.fail_compiler_batch(
                    batch.id,
                    error_type=type(exc).__name__,
                    error_message=error_message,
                )
                await repo.update_document_preprocessing_status(
                    document_id,
                    mode=mode,
                    status=PREPROCESSING_STATUS_FAILED,
                    error=error_message,
                    model=preprocessor.model_name,
                    prompt_version=prompt_version_for_mode(mode),
                    metrics={
                        "stage": "retry_failed_batches",
                        "status_message": (
                            "Повтор проблемной части завершился ошибкой"
                        ),
                        "error_type": type(exc).__name__,
                        "retried_batch_count": retried_batch_count,
                        "failed_batch_count_before": len(failed_batches),
                        "usage_event_count": usage_event_count,
                    },
                )
                await repo.update_document_status(document_id, "error", error_message)
                raise

        updated_batches = await repo.list_document_compiler_batches(
            project_id=project_id,
            document_id=document_id,
        )
        remaining_failed_count = sum(
            1 for batch in updated_batches if batch.status == "failed"
        )
        all_batches_completed = bool(updated_batches) and all(
            batch.status == "completed" for batch in updated_batches
        )
        raw_candidates = await repo.list_document_raw_answer_candidates(
            project_id=project_id,
            document_id=document_id,
        )
        canonical_entries: tuple[CanonicalKnowledgeEntry, ...] = ()

        if all_batches_completed:
            canonical_entries = _canonical_entries_from_raw_answer_candidates(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=updated_batches[0].compiler_run_id,
                mode=mode,
                candidates=raw_candidates,
            )
            if not canonical_entries:
                raise ValidationError(
                    "Knowledge retry produced no grounded answer entries"
                )
            await _persist_stage_e_compiler_outputs(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=updated_batches[0].compiler_run_id,
                source_chunks=source_chunks,
                entries=canonical_entries,
            )

        metrics: JsonObject = {
            "stage": "retry_failed_batches",
            "retried_batch_count": retried_batch_count,
            "failed_batch_count_before": len(failed_batches),
            "remaining_failed_batch_count": remaining_failed_count,
            "usage_event_count": usage_event_count,
            "raw_answer_count": len(raw_candidates),
            "canonical_entry_count": len(canonical_entries),
        }
        if all_batches_completed:
            metrics["status_message"] = (
                "Проблемные части повторены, ответы опубликованы"
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_COMPLETED,
                model=preprocessor.model_name,
                prompt_version=prompt_version_for_mode(mode),
                metrics=metrics,
            )
            await repo.update_document_status(document_id, "processed")
        else:
            metrics["status_message"] = (
                "Часть проблемных частей всё ещё требует повтора"
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_FAILED,
                model=preprocessor.model_name,
                prompt_version=prompt_version_for_mode(mode),
                metrics=metrics,
            )
            await repo.update_document_status(
                document_id,
                "error",
                "Some compiler batches still failed after retry",
            )
        logger.info(
            "Knowledge failed compiler batches retried",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "retried_batch_count": retried_batch_count,
                "remaining_failed_batch_count": remaining_failed_count,
            },
        )
        return {
            "status": "completed" if all_batches_completed else "partial",
            "document_id": document_id,
            "retried_batch_count": retried_batch_count,
            "remaining_failed_batch_count": remaining_failed_count,
            "usage_event_count": usage_event_count,
        }

    async def _process_document_faq_surface(
        self,
        *args: object,
        **kwargs: object,
    ) -> KnowledgeDocumentProcessingResult:
        raise KnowledgePreprocessingValidationError(
            "Bootstrap FAQ surface path was removed from the primary pipeline. "
            "FAQ uploads must use KnowledgeSurfaceCompilerPort.compile_surfaces via "
            "KnowledgeFaqSurfaceIngestionService."
        )

    async def process_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        chunks: list[JsonObject],
        mode: KnowledgePreprocessingMode,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort | None,
        logger: LoggerPort,
        commercial_price_repo_factory: CommercialPriceRepositoryFactoryPort
        | None = None,
        commercial_price_acquisition_service_factory: CommercialPriceAcquisitionServiceFactoryPort
        | None = None,
    ) -> KnowledgeDocumentProcessingResult:
        repo = knowledge_repo_factory(self.pool)
        usage_repo = model_usage_repo_factory(self.pool)
        await repo.cleanup_document_artifacts(
            build_document_reset_cleanup_plan(
                project_id=project_id,
                document_id=document_id,
            )
        )

        indexable_chunks = _indexable_chunks(chunks)
        if not indexable_chunks:
            message = "No indexable knowledge chunks after filtering"
            await repo.update_document_status(document_id, "error", message)
            raise ValidationError(message)

        compiler_source_chunks = _compiler_source_chunks_for_preprocessing(
            file_name=file_name,
            chunks=indexable_chunks,
            mode=mode,
        )
        source_chunks = _source_chunks_from_json_chunks(
            project_id=project_id,
            document_id=document_id,
            chunks=indexable_chunks,
        )
        if mode == MODE_PRICE_LIST and commercial_price_repo_factory is not None:
            price_result = (
                await CommercialPriceIngestionService().persist_price_source_material(
                    project_id=project_id,
                    knowledge_document_id=document_id,
                    file_name=file_name,
                    chunks=indexable_chunks,
                    price_repo=commercial_price_repo_factory(self.pool),
                    acquisition_service=(
                        commercial_price_acquisition_service_factory()
                        if commercial_price_acquisition_service_factory is not None
                        else None
                    ),
                )
            )
            logger.info(
                "Commercial price source material persisted",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "price_document_id": price_result.price_document_id,
                    "price_source_unit_count": price_result.source_unit_count,
                    "price_document_status": price_result.status.value,
                    "price_acquisition_row_count": price_result.acquisition_row_count,
                    "price_acquisition_fact_candidate_count": price_result.acquisition_fact_candidate_count,
                    "price_acquisition_issue_count": price_result.acquisition_issue_count,
                },
            )

        compiler_run_id = _stage_e_compiler_run_id(document_id=document_id, mode=mode)
        await repo.create_compiler_run(
            _stage_e_compiler_run(
                project_id=project_id,
                document_id=document_id,
                mode=mode,
                source_chunk_count=len(source_chunks),
            )
        )

        if preprocessor_factory is None:
            raise ValidationError(
                "Knowledge preprocessing adapter is required for price_list uploads"
            )

        await repo.add_source_chunks(
            project_id=project_id,
            document_id=document_id,
            chunks=source_chunks,
        )

        if mode == MODE_FAQ:
            return await self._process_document_faq_surface(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
                chunks=indexable_chunks,
                source_chunks=source_chunks,
            )

        await repo.update_document_preprocessing_status(
            document_id,
            mode=mode,
            status=PREPROCESSING_STATUS_PROCESSING,
        )

        active_model = ""
        active_prompt_version = prompt_version_for_mode(mode)
        technical_batches: tuple[list[JsonObject], ...] = ()

        try:
            preprocessor = preprocessor_factory()
            active_model = preprocessor.model_name
            technical_batches = tuple(
                _technical_chunk_batches_for_answer_compiler(compiler_source_chunks)
            )
            compiler_batches = _compiler_batches_from_technical_batches(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                technical_batches=technical_batches,
                source_chunks=source_chunks,
            )
            await repo.create_compiler_batches(
                project_id=project_id,
                document_id=document_id,
                batches=compiler_batches,
            )
            preprocessing_results: list[KnowledgePreprocessingResult] = []
            compiled_entries: list[KnowledgePreprocessingEntry] = []
            usage_event_count = 0
            llm_answer_resolution_call_count = 0
            answer_resolution_keep_separate_count = 0
            latest_result: KnowledgePreprocessingResult | None = None
            processing_started_monotonic = time.monotonic()

            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_PROCESSING,
                model=active_model,
                prompt_version=active_prompt_version,
                metrics={
                    "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                    "stage": "technical_compiler_loop",
                    "status_message": (
                        "Извлекаем смысловые ответы из документа и "
                        "привязываем их к источнику"
                    ),
                    "model": active_model,
                    "prompt_version": active_prompt_version,
                    "source_chunk_count": len(compiler_source_chunks),
                    "raw_source_chunk_count": len(indexable_chunks),
                    "markdown_semantic_units_total": (
                        len(compiler_source_chunks)
                        if _is_markdown_file(file_name)
                        else 0
                    ),
                    "markdown_semantic_units_processed": 0,
                    "markdown_child_sections_total": (
                        _json_array_field_item_count(
                            compiler_source_chunks,
                            "children",
                        )
                        if _is_markdown_file(file_name)
                        else 0
                    ),
                    "markdown_section_aware_batching": _is_markdown_file(file_name),
                    "technical_compiler_total_count": len(technical_batches),
                    "technical_source_char_budget": (
                        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                    ),
                    "technical_compiler_call_count": 0,
                    "technical_chunk_processed_count": 0,
                    "technical_chunk_total_count": len(technical_batches),
                    "compiled_entry_count": 0,
                    "semantic_answer_count": 0,
                    "incoming_entry_count": 0,
                    "extraction_concurrency": KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT,
                    "llm_answer_resolution_call_count": 0,
                    "semantic_answer_resolution_count": 0,
                    "answer_resolution_call_count": 0,
                    "usage_event_count": 0,
                    "elapsed_seconds": 0,
                    "previous_title_carryover": False,
                    "one_answer_at_a_time_resolution": False,
                    "answer_resolution_enabled": True,
                    "source_refs_preserved_per_semantic_entry": True,
                    "row_explosion_guard": (
                        "raw_source_chunks_not_persisted_as_runtime_entries"
                    ),
                },
            )

            progress_lock = asyncio.Lock()
            completed_batch_count = 0
            failed_batch_count = 0
            raw_candidate_count = 0
            entries_by_batch_index: dict[
                int, tuple[KnowledgePreprocessingEntry, ...]
            ] = {}
            results_by_batch_index: dict[int, KnowledgePreprocessingResult] = {}
            extraction_concurrency = KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT
            extraction_semaphore = asyncio.Semaphore(extraction_concurrency)

            async def process_compiler_batch(
                batch_index: int,
                technical_chunks: list[JsonObject],
                compiler_batch: CompilerBatch,
            ) -> None:
                nonlocal completed_batch_count
                nonlocal failed_batch_count
                nonlocal raw_candidate_count
                nonlocal usage_event_count
                nonlocal latest_result

                async with extraction_semaphore:
                    if await repo.is_document_processing_cancelled(document_id):
                        raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR)

                    await repo.mark_compiler_batch_processing(
                        compiler_batch.id,
                        attempt_count=compiler_batch.attempt_count + 1,
                    )

                    try:
                        execution = await preprocessor.preprocess(
                            mode=mode,
                            chunks=technical_chunks,
                            file_name=file_name,
                        )
                        if execution.usage is not None:
                            await usage_repo.record_event(
                                ModelUsageEventCreate.from_measurement(
                                    project_id=project_id,
                                    source="knowledge_preprocessing",
                                    measurement=execution.usage,
                                    document_id=document_id,
                                )
                            )

                        if await repo.is_document_processing_cancelled(document_id):
                            logger.info(
                                "Knowledge answer compiler batch result dropped after cancellation",
                                extra={
                                    "project_id": project_id,
                                    "document_id": document_id,
                                    "batch_index": batch_index,
                                    "batch_count": len(technical_batches),
                                    "model": execution.result.model,
                                    "requested_model": active_model,
                                },
                            )
                            raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR)

                        actual_model = execution.result.model
                        safe_entries = list(execution.result.entries)

                        raw_candidates = (
                            _raw_answer_candidates_from_preprocessing_entries(
                                project_id=project_id,
                                document_id=document_id,
                                compiler_run_id=compiler_run_id,
                                batch_id=compiler_batch.id,
                                batch_index=batch_index,
                                entries=safe_entries,
                                source_chunks=source_chunks,
                                mode=mode,
                            )
                        )
                        await repo.add_answer_candidates(
                            project_id=project_id,
                            document_id=document_id,
                            candidates=raw_candidates,
                        )
                        usage = execution.usage
                        await repo.complete_compiler_batch(
                            compiler_batch.id,
                            model=execution.result.model,
                            prompt_version=execution.result.prompt_version,
                            tokens_input=usage.tokens_input if usage is not None else 0,
                            tokens_output=usage.tokens_output
                            if usage is not None and usage.tokens_output is not None
                            else 0,
                            tokens_total=usage.tokens_total if usage is not None else 0,
                        )
                    except Exception as exc:
                        if str(exc) == KCD_STAGE_K_CANCELLED_ERROR or (
                            await repo.is_document_processing_cancelled(document_id)
                        ):
                            raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR) from exc

                        await repo.fail_compiler_batch(
                            compiler_batch.id,
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:500] or type(exc).__name__,
                        )
                        async with progress_lock:
                            failed_batch_count += 1
                            progress_metrics: JsonObject = {
                                "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                                "stage": "technical_compiler_loop",
                                "status_message": (
                                    "Обработка части завершилась с ошибкой; "
                                    "сохранённые черновики остаются доступными"
                                ),
                                "model": active_model,
                                "prompt_version": active_prompt_version,
                                "source_chunk_count": len(indexable_chunks),
                                "technical_compiler_total_count": len(
                                    technical_batches
                                ),
                                "technical_compiler_call_count": completed_batch_count,
                                "technical_chunk_processed_count": completed_batch_count,
                                "technical_chunk_total_count": len(technical_batches),
                                "failed_part_count": failed_batch_count,
                                "raw_draft_count": raw_candidate_count,
                                "compiled_entry_count": sum(
                                    len(entries)
                                    for entries in entries_by_batch_index.values()
                                ),
                                "answer_resolution_enabled": True,
                                "extraction_concurrency": extraction_concurrency,
                                "elapsed_seconds": round(
                                    time.monotonic() - processing_started_monotonic,
                                    1,
                                ),
                            }
                            await repo.update_document_preprocessing_status(
                                document_id,
                                mode=mode,
                                status=PREPROCESSING_STATUS_PROCESSING,
                                model=active_model,
                                prompt_version=active_prompt_version,
                                metrics=progress_metrics,
                            )
                        logger.warning(
                            "Knowledge answer compiler technical batch failed",
                            extra={
                                "project_id": project_id,
                                "document_id": document_id,
                                "batch_index": batch_index,
                                "batch_count": len(technical_batches),
                                "error_type": type(exc).__name__,
                            },
                        )
                        raise

                    async with progress_lock:
                        completed_batch_count += 1
                        raw_candidate_count += len(raw_candidates)
                        if execution.usage is not None:
                            usage_event_count += 1
                        latest_result = execution.result
                        preprocessing_results.append(execution.result)
                        results_by_batch_index[batch_index] = execution.result
                        entries_by_batch_index[batch_index] = tuple(safe_entries)
                        compiled_count = sum(
                            len(entries) for entries in entries_by_batch_index.values()
                        )
                        progress_metrics = {
                            "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                            "stage": "technical_compiler_loop",
                            "status_message": (
                                "Документ разбирается. Черновики сохраняются "
                                "после каждого шага."
                            ),
                            "model": actual_model,
                            "requested_model": active_model,
                            "actual_model": actual_model,
                            "prompt_version": active_prompt_version,
                            "source_chunk_count": len(compiler_source_chunks),
                            "raw_source_chunk_count": len(indexable_chunks),
                            "markdown_semantic_units_total": (
                                len(compiler_source_chunks)
                                if _is_markdown_file(file_name)
                                else 0
                            ),
                            "markdown_semantic_units_processed": completed_batch_count,
                            "markdown_section_aware_batching": _is_markdown_file(
                                file_name
                            ),
                            "technical_compiler_total_count": len(technical_batches),
                            "technical_source_char_budget": (
                                KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                            ),
                            "technical_compiler_call_count": completed_batch_count,
                            "technical_chunk_processed_count": completed_batch_count,
                            "technical_chunk_total_count": len(technical_batches),
                            "failed_part_count": failed_batch_count,
                            "raw_draft_count": raw_candidate_count,
                            "compiled_entry_count": compiled_count,
                            "semantic_answer_count": compiled_count,
                            "incoming_entry_count": len(execution.result.entries),
                            "llm_answer_resolution_call_count": llm_answer_resolution_call_count,
                            "semantic_answer_resolution_count": llm_answer_resolution_call_count,
                            "answer_resolution_call_count": llm_answer_resolution_call_count,
                            "answer_resolution_keep_separate_count": (
                                answer_resolution_keep_separate_count
                            ),
                            "usage_event_count": usage_event_count,
                            "answer_resolution_enabled": True,
                            "extraction_concurrency": extraction_concurrency,
                            "source_refs_preserved_per_semantic_entry": True,
                            "row_explosion_guard": (
                                "raw_source_chunks_not_persisted_as_runtime_entries"
                            ),
                            "elapsed_seconds": round(
                                time.monotonic() - processing_started_monotonic,
                                1,
                            ),
                        }
                        logger.info(
                            "Knowledge answer compiler technical batch completed",
                            extra={
                                "project_id": project_id,
                                "document_id": document_id,
                                "batch_index": batch_index,
                                "batch_count": len(technical_batches),
                                "extraction_status": "completed",
                                "raw_candidates_count": len(raw_candidates),
                                "compiled_entry_count": compiled_count,
                                "tokens": execution.usage.tokens_total
                                if execution.usage is not None
                                else 0,
                                "elapsed_seconds": progress_metrics["elapsed_seconds"],
                                "model": actual_model,
                                "requested_model": active_model,
                                "actual_model": actual_model,
                            },
                        )
                        await repo.update_document_preprocessing_status(
                            document_id,
                            mode=mode,
                            status=PREPROCESSING_STATUS_PROCESSING,
                            model=actual_model,
                            prompt_version=active_prompt_version,
                            metrics=progress_metrics,
                        )

            batch_tasks = [
                asyncio.create_task(
                    process_compiler_batch(
                        batch_index,
                        technical_chunks,
                        compiler_batches[batch_index - 1],
                    )
                )
                for batch_index, technical_chunks in enumerate(
                    technical_batches, start=1
                )
            ]
            batch_task_results = await asyncio.gather(
                *batch_tasks, return_exceptions=True
            )
            batch_errors = [
                result for result in batch_task_results if isinstance(result, Exception)
            ]
            if batch_errors:
                raise batch_errors[0]

            compiled_entries = [
                entry
                for batch_index in sorted(entries_by_batch_index)
                for entry in entries_by_batch_index[batch_index]
            ]
            latest_result = (
                results_by_batch_index[max(results_by_batch_index)]
                if results_by_batch_index
                else latest_result
            )

            if await repo.is_document_processing_cancelled(document_id):
                raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR)

            if latest_result is None:
                raise ValidationError("Knowledge preprocessing produced no results")

            source_excerpts_before_cleanup = tuple(
                _source_excerpts_from_preprocessing_entry(entry)
                for entry in compiled_entries
            )
            cleanup_result = _mechanically_cleanup_compiled_entries(
                entries=compiled_entries,
                source_excerpts_by_entry=source_excerpts_before_cleanup,
            )
            existing_project_titles = (
                await _existing_project_titles_for_answer_resolution(
                    repo=repo,
                    project_id=project_id,
                    document_id=document_id,
                )
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_PROCESSING,
                model=active_model,
                prompt_version=active_prompt_version,
                metrics={
                    "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                    "stage": "answer_resolution",
                    "status_message": (
                        "Извлечение завершено, идёт уплотнение повторяющихся смыслов."
                    ),
                    "technical_chunk_processed_count": len(technical_batches),
                    "technical_chunk_total_count": len(technical_batches),
                    "failed_part_count": 0,
                    "raw_draft_count": raw_candidate_count,
                    "compiled_entry_count": len(cleanup_result.entries),
                    "answer_resolution_enabled": True,
                    "extraction_concurrency": extraction_concurrency,
                    **cleanup_result.metrics,
                    "elapsed_seconds": round(
                        time.monotonic() - processing_started_monotonic,
                        1,
                    ),
                },
            )

            async def persist_answer_resolution_progress(metrics: JsonObject) -> None:
                await repo.update_document_preprocessing_status(
                    document_id,
                    mode=mode,
                    status=PREPROCESSING_STATUS_PROCESSING,
                    model=active_model,
                    prompt_version=active_prompt_version,
                    metrics={
                        "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                        "stage": "answer_resolution",
                        "status_message": (
                            "Черновики сохранены, идёт разрешение похожих ответов."
                        ),
                        "technical_chunk_processed_count": len(technical_batches),
                        "technical_chunk_total_count": len(technical_batches),
                        "failed_part_count": 0,
                        "raw_draft_count": raw_candidate_count,
                        "compiled_entry_count": len(cleanup_result.entries),
                        "deterministic_cleanup": cleanup_result.metrics,
                        "answer_resolution": {
                            **metrics,
                            "raw_draft_count": raw_candidate_count,
                        },
                        "answer_resolution_fallback_published": (
                            metrics.get("fallback_published") is True
                        ),
                        "answer_resolution_enabled": True,
                        "extraction_concurrency": extraction_concurrency,
                        "elapsed_seconds": round(
                            time.monotonic() - processing_started_monotonic,
                            1,
                        ),
                    },
                )

            answer_resolution_result = (
                await KnowledgeAnswerResolutionService().resolve_compiled_answer_cases(
                    preprocessor=preprocessor,
                    mode=mode,
                    file_name=file_name,
                    entries=cleanup_result.entries,
                    source_excerpts_by_entry=cleanup_result.source_excerpts_by_entry,
                    existing_project_titles=existing_project_titles,
                    on_progress=persist_answer_resolution_progress,
                )
            )
            tightened_entries = answer_resolution_result.entries
            tightened_source_excerpts = (
                answer_resolution_result.source_excerpts_by_entry
            )
            answer_resolution_metrics = answer_resolution_result.metrics
            regenerated_entries: list[KnowledgePreprocessingEntry] = []
            generated_entry_repair_warnings: list[tuple[str, ...]] = []
            for idx, generated_entry in enumerate(tightened_entries):
                raw_source_excerpt = (
                    tightened_source_excerpts[idx]
                    if idx < len(tightened_source_excerpts)
                    else (generated_entry.source_excerpt,)
                )
                source_text = _source_excerpt_to_text(raw_source_excerpt)
                repaired_entry, repair_warnings = _repair_generated_entry(
                    generated_entry,
                    source_excerpt=source_text,
                )
                regenerated_entries.append(repaired_entry)
                generated_entry_repair_warnings.append(repair_warnings)
            tightened_entries = tuple(regenerated_entries)
            answer_resolution_fallback_published = (
                answer_resolution_metrics.get("fallback_published") is True
            )
            if answer_resolution_fallback_published:
                answer_resolution_metrics["status"] = "failed_fallback_published"
                answer_resolution_metrics["published_fallback_entry_count"] = len(
                    tightened_entries
                )
                answer_resolution_metrics["raw_draft_count"] = raw_candidate_count
            llm_answer_resolution_call_count = _json_metric_int(
                answer_resolution_metrics, "llm_call_count"
            )
            answer_resolution_keep_separate_count = _json_metric_int(
                answer_resolution_metrics, "kept_separate_count"
            )

            result = _preprocessing_result_from_entries(
                mode=mode,
                template=latest_result,
                entries=tightened_entries,
                metrics={
                    "technical_compiler_call_count": len(preprocessing_results),
                    "technical_chunk_batch_size": (
                        KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL
                    ),
                    "technical_source_char_budget": (
                        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                    ),
                    "llm_answer_resolution_call_count": llm_answer_resolution_call_count,
                    "answer_resolution_keep_separate_count": (
                        answer_resolution_keep_separate_count
                    ),
                    "compiled_entry_key_count": len(tightened_entries),
                    "raw_draft_count": raw_candidate_count,
                    "deterministic_cleanup": cleanup_result.metrics,
                    "merged_preprocessing_entry_counts": cleanup_result.metrics.get(
                        "merged_preprocessing_entry_counts", []
                    ),
                    "source_refs_preserved_per_semantic_entry": True,
                    "answer_resolution": answer_resolution_metrics,
                    "answer_resolution_fallback_published": answer_resolution_fallback_published,
                    "answer_resolution_enabled": True,
                    "extraction_concurrency": extraction_concurrency,
                    "generated_entry_repair_warnings": [
                        list(item) for item in generated_entry_repair_warnings if item
                    ],
                },
            )
            canonical_entries = _canonical_entries_from_preprocessing_result(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                result=result,
                source_chunks=source_chunks,
            )
            if not canonical_entries:
                raise ValidationError(
                    "Knowledge preprocessing produced no grounded answer entries"
                )

            logger.info(
                "Knowledge answer compiler persistence audit",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "context": f"{mode}_answer_compiler_upload",
                    "source_chunk_count": len(source_chunks),
                    "llm_entry_count": len(result.entries),
                    "canonical_entry_count": len(canonical_entries),
                    "row_explosion_guard": (
                        "raw_source_chunks_not_persisted_as_runtime_entries"
                    ),
                    "metadata_preserved": True,
                    "source_refs_preserved_per_semantic_entry": True,
                },
            )

            await _persist_stage_e_compiler_outputs(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                source_chunks=source_chunks,
                entries=canonical_entries,
            )

            preprocessing_metrics: JsonObject = dict(result.metrics)
            preprocessing_metrics["raw_source_chunk_count"] = len(indexable_chunks)
            preprocessing_metrics["markdown_semantic_units_total"] = (
                len(compiler_source_chunks) if _is_markdown_file(file_name) else 0
            )
            preprocessing_metrics["markdown_semantic_units_processed"] = (
                len(compiler_source_chunks) if _is_markdown_file(file_name) else 0
            )
            preprocessing_metrics["markdown_child_sections_total"] = (
                _json_array_field_item_count(
                    compiler_source_chunks,
                    "children",
                )
                if _is_markdown_file(file_name)
                else 0
            )
            preprocessing_metrics["markdown_section_aware_batching"] = (
                _is_markdown_file(file_name)
            )
            preprocessing_metrics["llm_entry_count"] = len(result.entries)
            preprocessing_metrics["canonical_entry_count"] = len(canonical_entries)
            preprocessing_metrics["answer_compiler"] = KCD_STAGE_K_COMPILER_VERSION
            preprocessing_metrics["technical_compiler_call_count"] = len(
                preprocessing_results
            )
            preprocessing_metrics["technical_compiler_total_count"] = len(
                technical_batches
            )
            preprocessing_metrics["technical_chunk_total_count"] = len(
                technical_batches
            )
            preprocessing_metrics["technical_chunk_processed_count"] = len(
                technical_batches
            )
            preprocessing_metrics["semantic_answer_count"] = len(canonical_entries)
            preprocessing_metrics["published_entry_count"] = len(canonical_entries)
            preprocessing_metrics["model"] = result.model
            preprocessing_metrics["requested_model"] = active_model
            preprocessing_metrics["actual_model"] = result.model
            preprocessing_metrics["prompt_version"] = active_prompt_version
            preprocessing_metrics["stage"] = "completed"
            preprocessing_metrics["status_message"] = (
                "База знаний обновлена. Сырые черновики сохранены для проверки."
            )
            preprocessing_metrics["usage_event_count"] = usage_event_count
            preprocessing_metrics["llm_answer_resolution_call_count"] = (
                llm_answer_resolution_call_count
            )
            preprocessing_metrics["semantic_answer_resolution_count"] = (
                llm_answer_resolution_call_count
            )
            preprocessing_metrics["answer_resolution_call_count"] = (
                llm_answer_resolution_call_count
            )
            preprocessing_metrics["answer_resolution_keep_separate_count"] = (
                answer_resolution_keep_separate_count
            )
            preprocessing_metrics["elapsed_seconds"] = round(
                time.monotonic() - processing_started_monotonic,
                1,
            )
            preprocessing_metrics["previous_title_carryover"] = False
            preprocessing_metrics["one_answer_at_a_time_resolution"] = False
            preprocessing_metrics["one_meaning_at_a_time_extraction"] = True
            preprocessing_metrics["answer_resolution_enabled"] = True
            preprocessing_metrics["extraction_concurrency"] = extraction_concurrency
            preprocessing_metrics["raw_draft_count"] = raw_candidate_count
            preprocessing_metrics["duplicates_collapsed_safely_count"] = (
                _json_metric_int(
                    cleanup_result.metrics, "exact_duplicate_candidate_collapse_count"
                )
            )
            preprocessing_metrics["source_refs_preserved_per_semantic_entry"] = True
            preprocessing_metrics["row_explosion_guard"] = (
                "raw_source_chunks_not_persisted_as_runtime_entries"
            )

            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_COMPLETED,
                model=result.model,
                prompt_version=result.prompt_version,
                metrics=preprocessing_metrics,
            )
            await repo.update_document_status(document_id, "processed")
            return KnowledgeDocumentProcessingResult(
                document_id=document_id,
                preprocessing_status=PREPROCESSING_STATUS_COMPLETED,
                structured_entries=len(canonical_entries),
            )
        except EmbeddingProviderError as exc:
            if exc.retryable:
                logger.warning(
                    "Knowledge embedding provider temporary failure during structured indexing",
                    extra={
                        "project_id": project_id,
                        "document_id": document_id,
                        "provider": exc.provider,
                        "task": exc.task,
                        "model": exc.model,
                        "error_type": type(exc).__name__,
                    },
                )
                raise

            logger.warning(
                "Knowledge embedding provider permanent failure during structured indexing",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "provider": exc.provider,
                    "task": exc.task,
                    "model": exc.model,
                    "error_type": type(exc).__name__,
                },
            )
            await repo.update_document_status(document_id, "error", exc.detail)
            raise
        except KnowledgeDocumentDeletedDuringProcessingError as exc:
            logger.warning(
                "Knowledge document disappeared during structured indexing",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "mode": mode,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        except Exception as exc:
            error_message = str(exc)[:500] or type(exc).__name__
            logger.warning(
                "Knowledge preprocessing failed; structured pipeline stopped",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "mode": mode,
                    "error_type": type(exc).__name__,
                    "error": error_message,
                    "fallback": "disabled",
                },
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_FAILED,
                error=error_message,
                model=active_model or None,
                prompt_version=active_prompt_version,
                metrics={
                    "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                    "stage": "failed",
                    "status_message": _preprocessing_failure_status_message(exc),
                    "error_type": type(exc).__name__,
                    "fallback": "disabled",
                    "source_chunk_count": len(indexable_chunks),
                    "technical_compiler_total_count": len(technical_batches),
                    "technical_source_char_budget": (
                        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                    ),
                },
            )
            await repo.update_document_status(document_id, "error", error_message)
            raise ValidationError(error_message) from exc
