"""
Knowledge repository for RAG with hybrid search.

Clean Architecture contract:
- DB rows are converted to explicit typed read views inside this repository.
- Repository read methods do not return dict/Mapping compatibility objects.
"""

from __future__ import annotations

from src.domain.project_plane.knowledge_entry_kind import (
    RUNTIME_ENTRY_KIND_VALUES,
)

import json
from datetime import datetime
from typing import NoReturn

import asyncpg

from src.application.errors import (
    KnowledgeDocumentDeletedDuringProcessingError,
)

from src.domain.project_plane.knowledge_views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentView,
    KnowledgeSearchResultView,
)

from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_processing_modes import KnowledgeProcessingMode
from src.infrastructure.db.repositories.knowledge_search_ranking import (
    optional_row_text,
    optional_row_value,
    preview_score_and_trace,
    search_score_and_trace,
)
from src.infrastructure.db.repositories.knowledge_search_queries import (
    RUNTIME_HYBRID_SEARCH_SQL,
    RUNTIME_PREVIEW_SEARCH_SQL,
    RUNTIME_VECTOR_SEARCH_SQL,
)
from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
)
from src.contexts.embedding_runtime.infrastructure.composition.embedding_generation_provider_factory import (
    make_embedding_generation_port,
)
from src.contexts.embedding_runtime.infrastructure.config.embedding_runtime_settings import (
    EmbeddingRuntimeSettings,
    load_embedding_runtime_settings,
)
from src.infrastructure.logging.logger import get_logger
from src.utils.uuid_utils import ensure_uuid

from src.infrastructure.db.repositories.knowledge_db_codecs import (
    first_source_excerpt,
    pg_vector_text,
    source_ref_views_from_payload,
)
from src.infrastructure.db.repositories.knowledge_document_queries import (
    get_document_detail as query_document_detail,
    is_document_processing_cancelled as query_document_processing_cancelled,
    list_project_documents,
)
from src.infrastructure.db.repositories.knowledge_document_persistence import (
    create_document as persist_create_document,
    resume_document_processing as persist_resume_document_processing,
    update_document_preprocessing_status as persist_update_document_preprocessing_status,
    update_document_status as persist_update_document_status,
)


logger = get_logger(__name__)


def _raise_document_deleted_during_processing(
    exc: asyncpg.ForeignKeyViolationError,
) -> NoReturn:
    raise KnowledgeDocumentDeletedDuringProcessingError(
        "Knowledge document was deleted or reset during processing"
    ) from exc


CANCELLABLE_KNOWLEDGE_JOB_TYPES = (
    "process_knowledge_upload",
    "run_full_rag_eval",
)
TERMINAL_QUEUE_STATUSES = (
    "completed",
    "failed",
    "cancelled",
    "succeeded",
    "done",
)
ANSWERABLE_KNOWLEDGE_ENTRY_KINDS = tuple(sorted(RUNTIME_ENTRY_KIND_VALUES))


def _jsonb_array(value: object) -> str:
    if not isinstance(value, (list, tuple)):
        value = []
    return json.dumps(list(value), ensure_ascii=False)


def _surface_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class KnowledgeRepository:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        embedding_generation_port: EmbeddingGenerationPort | None = None,
        embedding_runtime_settings: EmbeddingRuntimeSettings | None = None,
    ) -> None:
        self.pool = pool
        self._embedding_runtime_settings = (
            embedding_runtime_settings or load_embedding_runtime_settings()
        )
        self._embedding_generation_port = (
            embedding_generation_port or make_embedding_generation_port()
        )

    async def resume_document_processing(
        self,
        *,
        project_id: str,
        document_id: str,
        mode: KnowledgeProcessingMode,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: JsonObject | None = None,
    ) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await persist_resume_document_processing(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    mode=mode,
                    model=model,
                    prompt_version=prompt_version,
                    metrics=metrics,
                )

    async def is_document_processing_cancelled(self, document_id: str) -> bool:
        async with self.pool.acquire() as conn:
            return await query_document_processing_cancelled(
                conn,
                document_id=document_id,
            )

    async def cleanup_document_artifacts(
        self, *args: object, **kwargs: object
    ) -> object:
        raise RuntimeError(
            "Legacy KnowledgeRepository artifact cleanup API is retired. "
            "Use Workbench delete/clear command handlers instead."
        )

    async def cleanup_project_artifacts(
        self, *args: object, **kwargs: object
    ) -> object:
        raise RuntimeError(
            "Legacy KnowledgeRepository artifact cleanup API is retired. "
            "Use Workbench delete/clear command handlers instead."
        )

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]:
        if limit <= 0:
            return []

        embedding_request = EmbeddingGenerationRequest(
            texts=(query,),
            model_id=self._embedding_runtime_settings.local_model,
            expected_dimensions=self._embedding_runtime_settings.vector_dimensions,
            task="retrieval.query",
        )
        query_embedding_result = await self._embedding_generation_port.embed(
            embedding_request
        )
        query_embedding = (
            query_embedding_result.embeddings[0]
            if query_embedding_result.embeddings
            else ()
        )
        query_embedding_str = pg_vector_text(list(query_embedding))
        project_uuid = ensure_uuid(project_id)

        candidate_limit = max(limit * 10, 50)

        async with self.pool.acquire() as conn:
            if not hybrid_fallback:
                rows = await conn.fetch(
                    RUNTIME_VECTOR_SEARCH_SQL,
                    query_embedding_str,
                    project_uuid,
                    limit,
                    list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
                    self._embedding_runtime_settings.local_model,
                    self._embedding_runtime_settings.vector_dimensions,
                )
            else:
                rows = await conn.fetch(
                    RUNTIME_HYBRID_SEARCH_SQL,
                    query_embedding_str,
                    query,
                    project_uuid,
                    candidate_limit,
                    candidate_limit,
                    list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
                    self._embedding_runtime_settings.local_model,
                    self._embedding_runtime_settings.vector_dimensions,
                )

        results: list[KnowledgeSearchResultView] = []

        for row in rows:
            content = str(row["content"])
            score_trace = search_score_and_trace(row, query=query, content=content)
            source_refs = source_ref_views_from_payload(
                optional_row_value(row, "source_refs")
            )
            results.append(
                KnowledgeSearchResultView(
                    id=str(row["id"]),
                    content=content,
                    score=score_trace.score,
                    method=score_trace.method,
                    document_id=optional_row_text(row, "document_id"),
                    source=optional_row_text(row, "source"),
                    document_status=optional_row_text(row, "document_status"),
                    entry_kind=optional_row_text(row, "entry_kind"),
                    title=optional_row_text(row, "title"),
                    source_excerpt=first_source_excerpt(source_refs),
                    source_refs=source_refs,
                    embedding_text=optional_row_text(row, "embedding_text"),
                    questions=optional_row_value(row, "questions"),
                    synonyms=optional_row_value(row, "synonyms"),
                    tags=optional_row_value(row, "tags"),
                    trace=score_trace.trace,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def preview_search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[KnowledgeSearchResultView]:
        """Debug-only lexical preview over published Workbench runtime entries."""
        if limit <= 0:
            return []

        normalized_query = query.strip()
        if not normalized_query:
            return []

        candidate_limit = max(limit * 12, 50)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                RUNTIME_PREVIEW_SEARCH_SQL,
                normalized_query,
                ensure_uuid(project_id),
                candidate_limit,
                list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
            )

        results: list[KnowledgeSearchResultView] = []
        for row in rows:
            content = str(row["content"])
            score_trace = preview_score_and_trace(
                row,
                query=normalized_query,
                content=content,
            )
            source_refs = source_ref_views_from_payload(
                optional_row_value(row, "source_refs")
            )
            results.append(
                KnowledgeSearchResultView(
                    id=str(row["id"]),
                    content=content,
                    score=score_trace.score,
                    method="workbench_runtime_lexical",
                    document_id=optional_row_text(row, "document_id"),
                    source=optional_row_text(row, "source"),
                    document_status=optional_row_text(row, "document_status"),
                    entry_kind=optional_row_text(row, "entry_kind"),
                    title=optional_row_text(row, "title"),
                    source_excerpt=first_source_excerpt(source_refs),
                    source_refs=source_refs,
                    embedding_text=optional_row_text(row, "embedding_text"),
                    questions=optional_row_value(row, "questions"),
                    synonyms=optional_row_value(row, "synonyms"),
                    tags=optional_row_value(row, "tags"),
                    trace=score_trace.trace,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def create_document(
        self,
        project_id: str,
        file_name: str,
        file_size: int | None = None,
        uploaded_by: str | None = None,
    ) -> str:
        logger.info(
            "Creating knowledge document",
            extra={"project_id": project_id, "file_name": file_name},
        )

        async with self.pool.acquire() as conn:
            document_id = await persist_create_document(
                conn,
                project_id=project_id,
                file_name=file_name,
                file_size=file_size,
                uploaded_by=uploaded_by,
            )

        logger.info("Document created", extra={"document_id": document_id})
        return document_id

    async def get_documents(
        self,
        project_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[KnowledgeDocumentView]:
        logger.debug(
            "Fetching knowledge documents",
            extra={"project_id": project_id, "limit": limit, "offset": offset},
        )

        async with self.pool.acquire() as conn:
            documents = await list_project_documents(
                conn,
                project_id=project_id,
                limit=limit,
                offset=offset,
            )

        logger.debug("Retrieved knowledge documents", extra={"count": len(documents)})
        return documents

    async def get_document(
        self, document_id: str
    ) -> KnowledgeDocumentDetailView | None:
        logger.debug("Fetching knowledge document", extra={"document_id": document_id})

        async with self.pool.acquire() as conn:
            return await query_document_detail(conn, document_id=document_id)

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        logger.info(
            "Updating document status",
            extra={"document_id": document_id, "status": status},
        )

        async with self.pool.acquire() as conn:
            await persist_update_document_status(
                conn,
                document_id=document_id,
                status=status,
                error=error,
            )

    async def update_document_preprocessing_status(
        self,
        document_id: str,
        *,
        mode: KnowledgeProcessingMode,
        status: str,
        error: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await persist_update_document_preprocessing_status(
                conn,
                document_id=document_id,
                mode=mode,
                status=status,
                error=error,
                model=model,
                prompt_version=prompt_version,
                metrics=metrics,
            )

    async def _cancel_document_jobs(
        self,
        conn: asyncpg.Connection,
        document_id: str,
    ) -> None:
        await conn.execute(
            """
            UPDATE execution_queue
            SET status = 'cancelled',
                error = COALESCE(
                    error,
                    'Cancelled because source knowledge document was deleted'
                ),
                updated_at = NOW()
            WHERE task_type = ANY($1::text[])
              AND COALESCE(status, '') <> ALL($2::text[])
              AND payload::jsonb ->> 'document_id' = $3
            """,
            list(CANCELLABLE_KNOWLEDGE_JOB_TYPES),
            list(TERMINAL_QUEUE_STATUSES),
            document_id,
        )

    async def _cancel_project_knowledge_jobs(
        self,
        conn: asyncpg.Connection,
        project_id: str,
    ) -> None:
        await conn.execute(
            """
            UPDATE execution_queue
            SET status = 'cancelled',
                error = COALESCE(
                    error,
                    'Cancelled because project knowledge base was cleared'
                ),
                updated_at = NOW()
            WHERE task_type = ANY($1::text[])
              AND COALESCE(status, '') <> ALL($2::text[])
              AND payload::jsonb ->> 'project_id' = $3
            """,
            list(CANCELLABLE_KNOWLEDGE_JOB_TYPES),
            list(TERMINAL_QUEUE_STATUSES),
            project_id,
        )

    async def delete_document_chunks(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError(
            "Legacy KnowledgeRepository artifact cleanup API is retired. "
            "Use Workbench delete/clear command handlers instead."
        )

    async def delete_document(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError(
            "Legacy KnowledgeRepository artifact cleanup API is retired. "
            "Use Workbench delete/clear command handlers instead."
        )

    async def clear_project_knowledge(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError(
            "Legacy KnowledgeRepository artifact cleanup API is retired. "
            "Use Workbench delete/clear command handlers instead."
        )
