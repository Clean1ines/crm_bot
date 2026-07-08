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

import asyncpg

from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchResultView,
)

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


logger = get_logger(__name__)


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
                    granularity=optional_row_text(row, "granularity"),
                    curation_item_ref=optional_row_text(row, "curation_item_ref"),
                    exclusion_scope=optional_row_text(row, "exclusion_scope"),
                    evidence_block=optional_row_text(row, "evidence_block"),
                    triples=optional_row_value(row, "triples"),
                    title=optional_row_text(row, "title"),
                    source_excerpt=first_source_excerpt(source_refs),
                    source_refs=source_refs,
                    raw_source_refs=optional_row_value(row, "raw_source_refs"),
                    source_claim_refs=optional_row_value(row, "source_claim_refs"),
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
                    granularity=optional_row_text(row, "granularity"),
                    curation_item_ref=optional_row_text(row, "curation_item_ref"),
                    exclusion_scope=optional_row_text(row, "exclusion_scope"),
                    evidence_block=optional_row_text(row, "evidence_block"),
                    triples=optional_row_value(row, "triples"),
                    title=optional_row_text(row, "title"),
                    source_excerpt=first_source_excerpt(source_refs),
                    source_refs=source_refs,
                    raw_source_refs=optional_row_value(row, "raw_source_refs"),
                    source_claim_refs=optional_row_value(row, "source_claim_refs"),
                    embedding_text=optional_row_text(row, "embedding_text"),
                    questions=optional_row_value(row, "questions"),
                    synonyms=optional_row_value(row, "synonyms"),
                    tags=optional_row_value(row, "tags"),
                    trace=score_trace.trace,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

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
