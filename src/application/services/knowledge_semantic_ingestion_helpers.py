from __future__ import annotations


import hashlib
import uuid
from collections.abc import Sequence
from src.application.errors import ValidationError
from src.application.ports.logger_port import LoggerPort
from src.application.services.knowledge_answer_compiler_batching import (
    KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL,
)
from src.application.services.knowledge_answer_resolution_service import (
    merge_answer_text,
)
from src.application.services.knowledge_canonical_publication_builder import (
    CompiledAnswerEntryDraft,
    build_answer_topic_key,
)
from src.application.services.knowledge_source_material_builder import chunk_content
from src.domain.project_plane.embedding_text import CANONICAL_EMBEDDING_TEXT_VERSION
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_chunks import (
    KnowledgeChunk,
    KnowledgeChunkDraft,
    KnowledgeChunkRole,
    KnowledgeSectionPath,
)
from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    KnowledgeEnrichment,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceChunk,
    SourceRef,
)
from src.domain.project_plane.knowledge_document_structure import (
    KnowledgeDocumentBlock,
    KnowledgeDocumentSource,
    ParsedKnowledgeDocument,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingResult,
)
from src.domain.project_plane.knowledge_semantic_builder import (
    build_knowledge_chunk_drafts,
    canonicalize_knowledge_chunk_drafts,
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

    content = chunk_content(chunk)
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
    content = chunk_content(chunk)
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

        content = chunk_content(chunk)
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
        content = chunk_content(chunk)
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


KCD_STAGE_E_COMPILER_VERSION = "kcd_v1_stage_e"


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


def source_excerpts_from_preprocessing_entry(
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
) -> CompiledAnswerEntryDraft:
    return CompiledAnswerEntryDraft(
        title=_clean_optional_text(entry.title) or f"Answer entry {index + 1}",
        answer=_clean_optional_text(entry.answer),
        source_excerpts=source_excerpts_from_preprocessing_entry(entry),
        source_refs=tuple(
            SourceRef(
                source_index=index,
                quote=source_excerpt,
                source_chunk_id=None,
                confidence=1.0,
            )
            for source_excerpt in source_excerpts_from_preprocessing_entry(entry)
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


def _merge_compiled_answer_drafts(
    left: CompiledAnswerEntryDraft,
    right: CompiledAnswerEntryDraft,
) -> CompiledAnswerEntryDraft:
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

    return CompiledAnswerEntryDraft(
        title=left.title,
        answer=merge_answer_text(left.answer, right.answer),
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
        embedding_text=merge_answer_text(left.embedding_text, right.embedding_text),
        metadata=metadata,
    )


def _compiled_answer_drafts_from_preprocessing_result(
    result: KnowledgePreprocessingResult,
) -> tuple[CompiledAnswerEntryDraft, ...]:
    grouped: dict[str, CompiledAnswerEntryDraft] = {}
    ordered_keys: list[str] = []

    for index, entry in enumerate(result.entries):
        draft = _preprocessing_entry_to_compiled_draft(
            entry,
            mode=result.mode,
            index=index,
        )
        if not draft.answer:
            continue

        key = build_answer_topic_key(entry, index=index)
        if key in grouped:
            grouped[key] = _merge_compiled_answer_drafts(grouped[key], draft)
            continue

        grouped[key] = draft
        ordered_keys.append(key)

    return tuple(grouped[key] for key in ordered_keys)


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


__all__ = [
    "_PLAIN_CHUNK_AUDIT_FIELDS",
    "SEMANTIC_CHUNK_METADATA_FIELDS",
    "_present_plain_chunk_value",
    "_plain_chunk_field_counts",
    "_log_plain_chunk_audit",
    "_clean_optional_text",
    "_text_tuple",
    "_has_semantic_chunk_metadata",
    "_role_from_entry_kind",
    "_draft_from_json_chunk",
    "_document_from_json_chunks",
    "_raw_chunks_for_structured_persistence",
    "_combined_chunks_for_canonical_persistence",
    "_merged_preprocessing_result",
    "_answer_titles_from_preprocessing_results",
    "_canonical_entries_from_knowledge_chunks",
]
