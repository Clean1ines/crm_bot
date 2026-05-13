import hashlib
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import asyncpg

from src.application.errors import EmbeddingProviderError, ValidationError
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    ModelUsageRepositoryFactoryPort,
    KnowledgePreprocessorFactoryPort,
    KnowledgeRepositoryFactoryPort,
    KnowledgeRepositoryPort,
)
from src.application.ports.logger_port import LoggerPort
from src.application.services.knowledge_normalization_service import (
    KnowledgeNormalizationService,
)
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
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
    MODE_PLAIN,
    PREPROCESSING_STATUS_COMPLETED,
    PREPROCESSING_STATUS_FAILED,
    PREPROCESSING_STATUS_NOT_REQUESTED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingResult,
    entry_kind_for_preprocessing_mode,
    prompt_version_for_mode,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate
from src.domain.project_plane.knowledge_compilation import (
    CompilerRunStatus,
    CompilerRun,
    CompilationMetrics,
    CandidateClusterStatus,
    CandidateCluster,
    AnswerCandidateStatus,
    AnswerCandidate,
    CanonicalKnowledgeEntry,
    KnowledgeEnrichment,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceChunk,
    SourceRef,
)


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


_MIN_INDEXABLE_CHUNK_CHARS = 1


def _chunk_content(chunk: JsonObject) -> str:
    return str(chunk.get("content") or "").strip()


def _is_separator_chunk(content: str) -> bool:
    normalized = " ".join(content.split())
    return normalized in {"---", "***", "___", "--", "-"} or bool(
        re.fullmatch(r"[-*_]{3,}", normalized)
    )


def _looks_like_broken_fragment(content: str) -> bool:
    normalized = " ".join(content.split())
    if not normalized:
        return True
    if _is_separator_chunk(normalized):
        return True
    if len(normalized) < _MIN_INDEXABLE_CHUNK_CHARS:
        return True
    if normalized[0] in {",", ";", ":", ".", ")", "]"}:
        return True

    # Keep this intentionally conservative. The raw/structured mixing fix is
    # the main production fix; this guard should only remove obvious garbage,
    # not compact but valid FAQ/test chunks.
    return False


def _indexable_chunks(chunks: list[JsonObject]) -> list[JsonObject]:
    return [
        chunk
        for chunk in chunks
        if not _looks_like_broken_fragment(_chunk_content(chunk))
    ]


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


def _split_technical_source_text(
    content: str,
    *,
    char_budget: int,
) -> tuple[str, ...]:
    text = content.strip()
    if not text:
        return ()
    if len(text) <= char_budget:
        return (text,)

    parts: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= char_budget:
            parts.append(remaining.strip())
            break

        window = remaining[:char_budget]
        cut = char_budget
        min_cut = max(120, char_budget // 3)

        for separator in ("\n\n", "\n", ". ", "; ", ", ", " "):
            position = window.rfind(separator)
            if position >= min_cut:
                cut = position + len(separator)
                break

        part = remaining[:cut].strip()
        if part:
            parts.append(part)
        remaining = remaining[cut:].strip()

    return tuple(part for part in parts if part)


def _technical_chunk_part(
    chunk: JsonObject,
    *,
    content: str,
    part_index: int,
    part_count: int,
) -> JsonObject:
    technical_chunk: JsonObject = {
        str(key): json_value_from_unknown(value) for key, value in chunk.items()
    }
    technical_chunk["content"] = content
    technical_chunk["technical_part_index"] = part_index
    technical_chunk["technical_part_count"] = part_count
    technical_chunk["technical_source_char_budget"] = (
        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
    )
    return technical_chunk


def _technical_chunk_batches_for_answer_compiler(
    chunks: list[JsonObject],
) -> tuple[list[JsonObject], ...]:
    batches: list[list[JsonObject]] = []

    for chunk in chunks:
        content = _chunk_content(chunk)
        if not content:
            continue

        parts = _split_technical_source_text(
            content,
            char_budget=KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET,
        )
        part_count = len(parts)

        for part_index, part_content in enumerate(parts, start=1):
            batches.append(
                [
                    _technical_chunk_part(
                        chunk,
                        content=part_content,
                        part_index=part_index,
                        part_count=part_count,
                    )
                ]
            )

    return tuple(batches)


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


def _source_chunk_optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        converted = int(value)
        return converted if converted >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        converted = int(value.strip())
        return converted if converted >= 0 else None
    return None


def _source_chunk_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _source_chunk_index(chunk: JsonObject, fallback_index: int) -> int:
    raw_index = _source_chunk_optional_int(chunk.get("index"))
    return raw_index if raw_index is not None else fallback_index


def _source_chunks_from_json_chunks(
    *,
    project_id: str,
    document_id: str,
    chunks: list[JsonObject],
) -> tuple[SourceChunk, ...]:
    source_chunks: list[SourceChunk] = []
    used_indices: set[int] = set()

    for fallback_index, chunk in enumerate(chunks):
        content = _chunk_content(chunk)
        if not content:
            continue

        source_index = _source_chunk_index(chunk, fallback_index)
        while source_index in used_indices:
            source_index += 1
        used_indices.add(source_index)

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata: dict[str, object] = {"upload_chunk_index": fallback_index}

        source_chunks.append(
            SourceChunk(
                id=f"{document_id}:{source_index}",
                document_id=document_id,
                project_id=project_id,
                source_index=source_index,
                content=content,
                page=_source_chunk_optional_int(chunk.get("page")),
                section_title=_source_chunk_text(
                    chunk.get("section_title") or chunk.get("title")
                ),
                start_offset=_source_chunk_optional_int(chunk.get("start_offset")),
                end_offset=_source_chunk_optional_int(chunk.get("end_offset")),
                checksum=checksum,
                metadata=metadata,
            )
        )

    return tuple(source_chunks)


KCD_STAGE_CD_COMPILER_VERSION = "kcd_v1_stage_cd"
KCD_STAGE_E_COMPILER_VERSION = "kcd_v1_stage_e"
KCD_STAGE_K_COMPILER_VERSION = "kcd_v1_stage_k_answer_compiler"
KCD_STAGE_K_CANCELLED_ERROR = "Knowledge preprocessing cancelled by operator"
KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL = 1
KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET = 650
KCD_STAGE_K_PREVIOUS_TITLE_LIMIT = 80


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


@dataclass(frozen=True, slots=True)
class _CompiledAnswerEntryDraft:
    title: str
    answer: str
    source_excerpts: tuple[str, ...]
    source_refs: tuple[SourceRef, ...]
    questions: tuple[str, ...]
    synonyms: tuple[str, ...]
    tags: tuple[str, ...]
    embedding_text: str
    metadata: Mapping[str, object]


def _normalized_answer_topic_key(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def _answer_topic_key(entry: KnowledgePreprocessingEntry, *, index: int) -> str:
    title_key = _normalized_answer_topic_key(entry.title)
    if title_key:
        return title_key

    answer_key = _normalized_answer_topic_key(entry.answer)
    if answer_key:
        return answer_key[:160]

    return f"entry-{index}"


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


def _merge_answer_text(left: str, right: str) -> str:
    left_clean = _clean_optional_text(left)
    right_clean = _clean_optional_text(right)

    if not left_clean:
        return right_clean
    if not right_clean:
        return left_clean

    left_normalized = _normalized_answer_topic_key(left_clean)
    right_normalized = _normalized_answer_topic_key(right_clean)

    if left_normalized == right_normalized:
        return left_clean
    if right_normalized and right_normalized in left_normalized:
        return left_clean
    if left_normalized and left_normalized in right_normalized:
        return right_clean

    return f"{left_clean}\n\n{right_clean}"


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
    metadata["compiler_merge"] = "normalized_title"
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


def _merge_source_excerpt_text(
    *entries: KnowledgePreprocessingEntry,
) -> str:
    excerpts: list[str] = []

    for entry in entries:
        for excerpt in _source_excerpts_from_preprocessing_entry(entry):
            if excerpt and excerpt not in excerpts:
                excerpts.append(excerpt)

    return "\n\n".join(excerpts)


KCD_STAGE_K_MERGED_QUESTION_LIMIT = 40
KCD_STAGE_K_MERGED_SYNONYM_LIMIT = 64
KCD_STAGE_K_MERGED_TAG_LIMIT = 32
KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS = 3600
KCD_STAGE_K_MERGED_SOURCE_EXCERPT_MAX_CHARS = 7000
KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS = 2400


def _limit_compiled_text(value: str, *, max_chars: int) -> str:
    cleaned = _clean_optional_text(value)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip()


def _merge_limited_text_tuple_values(
    *groups: tuple[str, ...],
    limit: int,
) -> tuple[str, ...]:
    return _merge_text_tuple_values(*groups)[:limit]


def _merge_entry_fields_deterministically(
    *,
    existing_entry: KnowledgePreprocessingEntry,
    incoming_entry: KnowledgePreprocessingEntry,
    merged_embedding_text: str,
) -> KnowledgePreprocessingEntry:
    answer = _limit_compiled_text(
        _merge_answer_text(existing_entry.answer, incoming_entry.answer),
        max_chars=KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS,
    )
    source_excerpt = _limit_compiled_text(
        _merge_source_excerpt_text(existing_entry, incoming_entry),
        max_chars=KCD_STAGE_K_MERGED_SOURCE_EXCERPT_MAX_CHARS,
    )
    embedding_text = _limit_compiled_text(
        merged_embedding_text,
        max_chars=KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS,
    )

    if not embedding_text:
        embedding_text = _limit_compiled_text(
            _merge_answer_text(
                existing_entry.embedding_text,
                incoming_entry.embedding_text,
            ),
            max_chars=KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS,
        )

    return KnowledgePreprocessingEntry(
        title=_clean_optional_text(existing_entry.title)
        or _clean_optional_text(incoming_entry.title),
        answer=answer,
        source_excerpt=source_excerpt,
        questions=_merge_limited_text_tuple_values(
            _text_tuple(existing_entry.questions),
            _text_tuple(incoming_entry.questions),
            limit=KCD_STAGE_K_MERGED_QUESTION_LIMIT,
        ),
        synonyms=_merge_limited_text_tuple_values(
            _text_tuple(existing_entry.synonyms),
            _text_tuple(incoming_entry.synonyms),
            limit=KCD_STAGE_K_MERGED_SYNONYM_LIMIT,
        ),
        tags=_merge_limited_text_tuple_values(
            _text_tuple(existing_entry.tags),
            _text_tuple(incoming_entry.tags),
            limit=KCD_STAGE_K_MERGED_TAG_LIMIT,
        ),
        embedding_text=embedding_text,
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


def _source_chunk_for_quote(
    *,
    quote: str,
    source_chunks: Sequence[SourceChunk],
) -> SourceChunk:
    if not source_chunks:
        raise ValidationError("Cannot ground answer entry without source chunks")

    quote_clean = _clean_optional_text(quote)
    if quote_clean:
        for source_chunk in source_chunks:
            if (
                quote_clean in source_chunk.content
                or source_chunk.content in quote_clean
            ):
                return source_chunk

    quote_terms = {
        token
        for token in re.findall(
            r"[0-9a-zа-яё]+",
            quote_clean.lower().replace("ё", "е"),
        )
        if len(token) >= 4
    }

    if quote_terms:
        best_chunk = source_chunks[0]
        best_score = -1
        for source_chunk in source_chunks:
            chunk_terms = {
                token
                for token in re.findall(
                    r"[0-9a-zа-яё]+",
                    source_chunk.content.lower().replace("ё", "е"),
                )
                if len(token) >= 4
            }
            score = len(quote_terms & chunk_terms)
            if score > best_score:
                best_chunk = source_chunk
                best_score = score
        return best_chunk

    return source_chunks[0]


def _source_refs_for_compiled_answer_draft(
    *,
    draft: _CompiledAnswerEntryDraft,
    source_chunks: Sequence[SourceChunk],
) -> tuple[SourceRef, ...]:
    refs: list[SourceRef] = []
    seen_quotes: set[str] = set()

    quotes = draft.source_excerpts or (draft.answer,)
    for quote in quotes:
        cleaned_quote = _clean_optional_text(quote)
        if not cleaned_quote or cleaned_quote in seen_quotes:
            continue

        source_chunk = _source_chunk_for_quote(
            quote=cleaned_quote,
            source_chunks=source_chunks,
        )
        refs.append(
            SourceRef(
                source_index=source_chunk.source_index,
                quote=cleaned_quote,
                source_chunk_id=source_chunk.id,
                start_offset=source_chunk.start_offset,
                end_offset=source_chunk.end_offset,
                confidence=1.0,
            )
        )
        seen_quotes.add(cleaned_quote)

    return tuple(refs)


def _canonical_entries_from_preprocessing_result(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    result: KnowledgePreprocessingResult,
    source_chunks: Sequence[SourceChunk],
    source_excerpts_by_entry: Sequence[tuple[str, ...]] | None = None,
) -> tuple[CanonicalKnowledgeEntry, ...]:
    drafts = _compiled_answer_drafts_from_preprocessing_result(result)
    if source_excerpts_by_entry is not None and len(source_excerpts_by_entry) != len(
        drafts
    ):
        raise ValidationError(
            "Preserved source excerpts must match compiled answer draft count"
        )

    entry_kind = entry_kind_for_preprocessing_mode(result.mode)
    entries: list[CanonicalKnowledgeEntry] = []

    for index, draft in enumerate(drafts):
        preserved_source_excerpts = (
            source_excerpts_by_entry[index]
            if source_excerpts_by_entry is not None
            else ()
        )
        source_ref_draft = (
            _CompiledAnswerEntryDraft(
                title=draft.title,
                answer=draft.answer,
                source_excerpts=preserved_source_excerpts,
                source_refs=(),
                questions=draft.questions,
                synonyms=draft.synonyms,
                tags=draft.tags,
                embedding_text=draft.embedding_text,
                metadata=draft.metadata,
            )
            if preserved_source_excerpts
            else draft
        )
        source_refs = _source_refs_for_compiled_answer_draft(
            draft=source_ref_draft,
            source_chunks=source_chunks,
        )
        stable_key_digest = hashlib.sha256(
            (
                f"{document_id}:stage_k:{entry_kind.value}:{draft.title}:{draft.answer}"
            ).encode("utf-8")
        ).hexdigest()
        stable_key = f"{document_id}:stage_k:{stable_key_digest[:24]}"
        entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))
        metadata: dict[str, object] = dict(draft.metadata)
        metadata["source_ref_count"] = len(source_refs)
        metadata["compiler_index"] = index

        entry = CanonicalKnowledgeEntry(
            id=entry_id,
            project_id=project_id,
            document_id=document_id,
            compiler_run_id=compiler_run_id,
            stable_key=stable_key,
            entry_kind=entry_kind,
            title=draft.title,
            answer=draft.answer,
            source_refs=source_refs,
            enrichment=KnowledgeEnrichment(
                questions=draft.questions,
                synonyms=draft.synonyms,
                tags=draft.tags,
            ),
            embedding_text=None,
            status=KnowledgeEntryStatus.PUBLISHED,
            visibility=KnowledgeEntryVisibility.RUNTIME,
            version=1,
            compiler_version=KCD_STAGE_K_COMPILER_VERSION,
            embedding_text_version=CANONICAL_EMBEDDING_TEXT_VERSION,
            metadata=metadata,
        )
        entry.assert_publishable()
        entries.append(entry)

    return tuple(entries)


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
        compiler_version=KCD_STAGE_E_COMPILER_VERSION
        if mode == MODE_PLAIN
        else KCD_STAGE_K_COMPILER_VERSION,
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
    repo: KnowledgeRepositoryPort,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    source_chunks: Sequence[SourceChunk],
    entries: Sequence[CanonicalKnowledgeEntry],
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
        repo: KnowledgeRepositoryPort,
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
        except asyncpg.ForeignKeyViolationError as exc:
            logger.warning(
                "Knowledge document disappeared before plain chunks were persisted",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "context": context,
                    "error_type": type(exc).__name__,
                },
            )
            raise ValidationError(
                "Knowledge document was deleted before chunk persistence completed"
            ) from exc
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

    async def process_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        chunks: list[JsonObject],
        mode: KnowledgePreprocessingMode,
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort | None,
        logger: LoggerPort,
    ) -> KnowledgeDocumentProcessingResult:
        repo = knowledge_repo_factory(self.pool)
        usage_repo = model_usage_repo_factory(self.pool)
        await repo.delete_document_chunks(document_id)

        indexable_chunks = _indexable_chunks(chunks)
        if not indexable_chunks:
            message = "No indexable knowledge chunks after filtering"
            await repo.update_document_status(document_id, "error", message)
            raise ValidationError(message)

        source_chunks = _source_chunks_from_json_chunks(
            project_id=project_id,
            document_id=document_id,
            chunks=indexable_chunks,
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

        if mode == MODE_PLAIN:
            await repo.add_source_chunks(
                project_id=project_id,
                document_id=document_id,
                chunks=source_chunks,
            )
            await self._persist_plain_chunks(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
                file_name=file_name,
                chunks=indexable_chunks,
                source_chunks=source_chunks,
                compiler_run_id=compiler_run_id,
                logger=logger,
                context="plain_upload",
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_NOT_REQUESTED,
            )
            await repo.update_document_status(document_id, "processed")
            return KnowledgeDocumentProcessingResult(
                document_id=document_id,
                preprocessing_status=PREPROCESSING_STATUS_NOT_REQUESTED,
                structured_entries=0,
            )

        if preprocessor_factory is None:
            raise ValidationError(
                "Knowledge preprocessing adapter is required for non-plain upload modes"
            )

        await repo.add_source_chunks(
            project_id=project_id,
            document_id=document_id,
            chunks=source_chunks,
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
                _technical_chunk_batches_for_answer_compiler(indexable_chunks)
            )
            preprocessing_results: list[KnowledgePreprocessingResult] = []
            compiled_entries: list[KnowledgePreprocessingEntry] = []
            compiled_entry_source_excerpts: list[tuple[str, ...]] = []
            compiled_entry_keys: list[str] = []
            compiled_entry_index_by_key: dict[str, int] = {}
            usage_event_count = 0
            llm_merge_call_count = 0
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
                    "source_chunk_count": len(indexable_chunks),
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
                    "previous_title_count": 0,
                    "llm_merge_call_count": 0,
                    "semantic_answer_merge_count": 0,
                    "embedding_text_merge_call_count": 0,
                    "usage_event_count": 0,
                    "elapsed_seconds": 0,
                    "previous_title_carryover": True,
                    "one_meaning_at_a_time_merge": True,
                    "source_refs_preserved_per_semantic_entry": True,
                    "row_explosion_guard": (
                        "raw_source_chunks_not_persisted_as_runtime_entries"
                    ),
                },
            )

            for batch_index, technical_chunks in enumerate(technical_batches, start=1):
                if await repo.is_document_processing_cancelled(document_id):
                    raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR)

                previous_entry_titles = tuple(entry.title for entry in compiled_entries)
                execution = await preprocessor.preprocess(
                    mode=mode,
                    chunks=technical_chunks,
                    file_name=file_name,
                    previous_entry_titles=previous_entry_titles[
                        -KCD_STAGE_K_PREVIOUS_TITLE_LIMIT:
                    ],
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

                latest_result = execution.result
                preprocessing_results.append(execution.result)

                for incoming_entry in execution.result.entries:
                    entry_key = _answer_topic_key(
                        incoming_entry,
                        index=len(compiled_entries),
                    )
                    incoming_source_excerpts = (
                        _source_excerpts_from_preprocessing_entry(incoming_entry)
                    )
                    if entry_key not in compiled_entry_index_by_key:
                        compiled_entry_index_by_key[entry_key] = len(compiled_entries)
                        compiled_entry_keys.append(entry_key)
                        compiled_entries.append(incoming_entry)
                        compiled_entry_source_excerpts.append(incoming_source_excerpts)
                        continue

                    existing_index = compiled_entry_index_by_key[entry_key]
                    existing_entry = compiled_entries[existing_index]
                    embedding_text_merge_execution = (
                        await preprocessor.merge_embedding_text(
                            mode=mode,
                            file_name=file_name,
                            title=existing_entry.title,
                            existing_embedding_text=existing_entry.embedding_text,
                            incoming_embedding_text=incoming_entry.embedding_text,
                        )
                    )
                    if embedding_text_merge_execution.usage is not None:
                        await usage_repo.record_event(
                            ModelUsageEventCreate.from_measurement(
                                project_id=project_id,
                                source="knowledge_preprocessing",
                                measurement=embedding_text_merge_execution.usage,
                                document_id=document_id,
                            )
                        )
                        usage_event_count += 1

                    compiled_entries[existing_index] = (
                        _merge_entry_fields_deterministically(
                            existing_entry=existing_entry,
                            incoming_entry=incoming_entry,
                            merged_embedding_text=(
                                embedding_text_merge_execution.embedding_text
                            ),
                        )
                    )
                    compiled_entry_source_excerpts[existing_index] = (
                        _merge_text_tuple_values(
                            compiled_entry_source_excerpts[existing_index],
                            incoming_source_excerpts,
                        )
                    )
                    llm_merge_call_count += 1

                progress_metrics: JsonObject = {
                    "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                    "stage": "technical_compiler_loop",
                    "status_message": (
                        "Извлекаем смысловые ответы из документа и объединяем повторы"
                    ),
                    "model": active_model,
                    "prompt_version": active_prompt_version,
                    "source_chunk_count": len(indexable_chunks),
                    "technical_compiler_total_count": len(technical_batches),
                    "technical_source_char_budget": (
                        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                    ),
                    "technical_compiler_call_count": batch_index,
                    "technical_chunk_processed_count": batch_index,
                    "technical_chunk_total_count": len(technical_batches),
                    "compiled_entry_count": len(compiled_entries),
                    "semantic_answer_count": len(compiled_entries),
                    "incoming_entry_count": len(execution.result.entries),
                    "previous_title_count": len(previous_entry_titles),
                    "llm_merge_call_count": llm_merge_call_count,
                    "semantic_answer_merge_count": llm_merge_call_count,
                    "embedding_text_merge_call_count": llm_merge_call_count,
                    "usage_event_count": usage_event_count,
                    "elapsed_seconds": round(
                        time.monotonic() - processing_started_monotonic,
                        1,
                    ),
                    "previous_title_carryover": True,
                    "one_meaning_at_a_time_merge": True,
                    "source_refs_preserved_per_semantic_entry": True,
                    "row_explosion_guard": (
                        "raw_source_chunks_not_persisted_as_runtime_entries"
                    ),
                }
                logger.info(
                    "Knowledge answer compiler technical batch processed",
                    extra={
                        "project_id": project_id,
                        "document_id": document_id,
                        "batch_index": batch_index,
                        "batch_count": len(technical_batches),
                        "source_chunk_count": len(indexable_chunks),
                        "previous_title_count": len(previous_entry_titles),
                        "incoming_entry_count": len(execution.result.entries),
                        "compiled_entry_count": len(compiled_entries),
                        "llm_merge_call_count": llm_merge_call_count,
                        "model": active_model,
                    },
                )
                await repo.update_document_preprocessing_status(
                    document_id,
                    mode=mode,
                    status=PREPROCESSING_STATUS_PROCESSING,
                    model=active_model,
                    prompt_version=active_prompt_version,
                    metrics=progress_metrics,
                )

            if await repo.is_document_processing_cancelled(document_id):
                raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR)

            if latest_result is None:
                raise ValidationError("Knowledge preprocessing produced no results")

            result = _preprocessing_result_from_entries(
                mode=mode,
                template=latest_result,
                entries=compiled_entries,
                metrics={
                    "technical_compiler_call_count": len(preprocessing_results),
                    "technical_chunk_batch_size": (
                        KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL
                    ),
                    "technical_source_char_budget": (
                        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                    ),
                    "llm_merge_call_count": llm_merge_call_count,
                    "compiled_entry_key_count": len(compiled_entry_keys),
                    "source_refs_preserved_per_semantic_entry": True,
                },
            )
            canonical_entries = _canonical_entries_from_preprocessing_result(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                result=result,
                source_chunks=source_chunks,
                source_excerpts_by_entry=compiled_entry_source_excerpts,
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
            preprocessing_metrics["model"] = active_model
            preprocessing_metrics["prompt_version"] = active_prompt_version
            preprocessing_metrics["stage"] = "completed"
            preprocessing_metrics["status_message"] = (
                "Документ обработан: смысловые ответы собраны и опубликованы"
            )
            preprocessing_metrics["usage_event_count"] = usage_event_count
            preprocessing_metrics["llm_merge_call_count"] = llm_merge_call_count
            preprocessing_metrics["semantic_answer_merge_count"] = llm_merge_call_count
            preprocessing_metrics["embedding_text_merge_call_count"] = (
                llm_merge_call_count
            )
            preprocessing_metrics["elapsed_seconds"] = round(
                time.monotonic() - processing_started_monotonic,
                1,
            )
            preprocessing_metrics["previous_title_carryover"] = True
            preprocessing_metrics["one_meaning_at_a_time_merge"] = True
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
        except asyncpg.ForeignKeyViolationError as exc:
            logger.warning(
                "Knowledge document disappeared during structured indexing",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "mode": mode,
                    "error_type": type(exc).__name__,
                },
            )
            raise ValidationError(
                "Knowledge document was deleted before structured indexing completed"
            ) from exc
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
                    "status_message": (
                        "Ошибка предобработки: LLM не вернула корректный JSON"
                    ),
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
