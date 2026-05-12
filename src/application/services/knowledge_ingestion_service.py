import re
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
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_chunks import (
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
    KnowledgePreprocessingMode,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate
import hashlib
from src.domain.project_plane.knowledge_compilation import SourceChunk


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
            await repo.add_knowledge_chunks(
                project_id=project_id,
                document_id=document_id,
                chunks=normalized.chunks,
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

        try:
            execution = await preprocessor_factory().preprocess(
                mode=mode,
                chunks=indexable_chunks,
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

            result = execution.result
            structured_chunks = _indexable_chunks(result.to_chunks())
            if not structured_chunks:
                raise ValidationError(
                    "Knowledge preprocessing produced no indexable structured chunks"
                )

            canonical_chunks = _combined_chunks_for_canonical_persistence(
                raw_chunks=indexable_chunks,
                structured_chunks=structured_chunks,
            )
            document = _document_from_json_chunks(
                file_name=file_name,
                chunks=canonical_chunks,
            )
            normalized = KnowledgeNormalizationService().normalize_document(
                document,
                project_id=project_id,
                document_id=document_id,
            )
            _log_plain_chunk_audit(
                logger,
                project_id=project_id,
                document_id=document_id,
                chunks=canonical_chunks,
                context=f"{mode}_canonical_upload",
            )
            await repo.add_knowledge_chunks(
                project_id=project_id,
                document_id=document_id,
                chunks=normalized.chunks,
            )

            preprocessing_metrics: JsonObject = dict(result.metrics)
            preprocessing_metrics["raw_chunk_count"] = len(indexable_chunks)
            preprocessing_metrics["structured_chunk_count"] = len(structured_chunks)
            preprocessing_metrics["canonical_chunk_count"] = len(normalized.chunks)

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
                structured_entries=len(structured_chunks),
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
            logger.warning(
                "Knowledge preprocessing failed; original chunks remain usable",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "mode": mode,
                    "error_type": type(exc).__name__,
                },
            )
            await self._persist_plain_chunks(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
                file_name=file_name,
                chunks=indexable_chunks,
                logger=logger,
                context="preprocessing_fallback",
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_FAILED,
                error=str(exc)[:1000],
            )
            await repo.update_document_status(document_id, "processed")
            return KnowledgeDocumentProcessingResult(
                document_id=document_id,
                preprocessing_status=PREPROCESSING_STATUS_FAILED,
                structured_entries=0,
            )
