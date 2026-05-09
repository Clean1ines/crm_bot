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
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_PLAIN,
    PREPROCESSING_STATUS_COMPLETED,
    PREPROCESSING_STATUS_FAILED,
    PREPROCESSING_STATUS_NOT_REQUESTED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingMode,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate


_PLAIN_CHUNK_AUDIT_FIELDS: tuple[str, ...] = (
    "content",
    "entry_type",
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


def _raw_chunks_for_structured_persistence(
    chunks: list[JsonObject],
) -> list[JsonObject]:
    """Preserve source chunks when LLM preprocessing enriches a document.

    LLM preprocessing may add normalized FAQ/price/instruction entries, but it
    must never be the only persisted representation of the uploaded document.

    Important: source chunks may already be enriched by the deterministic
    chunker. Do not collapse them back to legacy ``entry_type="chunk"`` rows,
    otherwise markdown titles, source excerpts, tags and embedding_text are
    lost in FAQ/structured preprocessing modes.
    """
    raw_chunks: list[JsonObject] = []
    metadata_fields = (
        "entry_type",
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

        if not _present_plain_chunk_value(preserved.get("entry_type")):
            preserved["entry_type"] = "chunk"

        if not _present_plain_chunk_value(preserved.get("embedding_text")):
            preserved["embedding_text"] = content

        raw_chunks.append(preserved)

    return raw_chunks


class KnowledgeIngestionService:
    def __init__(self, pool: KnowledgeDbPoolPort) -> None:
        self.pool = pool

    async def _persist_plain_chunks(
        self,
        *,
        repo: KnowledgeRepositoryPort,
        project_id: str,
        document_id: str,
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
        try:
            await repo.add_knowledge_batch(project_id, chunks, document_id=document_id)
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

        if mode == MODE_PLAIN:
            await self._persist_plain_chunks(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
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

            raw_chunks = _raw_chunks_for_structured_persistence(indexable_chunks)
            chunks_to_persist = [*structured_chunks, *raw_chunks]
            preprocessing_metrics: JsonObject = {
                **result.metrics,
                "structured_entries": len(structured_chunks),
                "raw_chunks_preserved": len(raw_chunks),
                "persisted_chunks": len(chunks_to_persist),
                "lossless_preprocessing": True,
            }

            await repo.add_structured_knowledge_batch(
                project_id,
                chunks_to_persist,
                document_id=document_id,
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
