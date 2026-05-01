"""
Knowledge repository for RAG with hybrid search.

Clean Architecture contract:
- DB rows are converted to explicit typed read views inside this repository.
- Repository read methods do not return dict/Mapping compatibility objects.
"""

import json
from collections.abc import Iterator
from typing import Protocol

import asyncpg

from src.domain.project_plane.knowledge_views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentView,
    KnowledgeSearchResultView,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode
from src.infrastructure.llm.embedding_service import embed_batch, embed_text
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from src.utils.uuid_utils import ensure_uuid


logger = get_logger(__name__)


class _RowLookup(Protocol):
    def __getitem__(self, key: str) -> object: ...


def _optional_row_text(row: _RowLookup, key: str) -> str | None:
    try:
        value = row[key]
    except KeyError:
        return None

    return str(value) if value is not None else None


def _normalize_timestamp(value: object) -> str | None:
    """
    Keep test strings unchanged and serialize real datetime-like values only
    when the repository owns the DB-row normalization boundary.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _jsonb_array(value: object) -> str:
    if not isinstance(value, list):
        value = []
    return json.dumps(value, ensure_ascii=False)


def _pg_vector_text(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _batched_chunks(
    chunks: list[JsonObject], batch_size: int
) -> Iterator[list[JsonObject]]:
    for start in range(0, len(chunks), batch_size):
        yield chunks[start : start + batch_size]


class KnowledgeRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    def _keyword_overlap(self, query: str, text: str) -> float:
        q = set(query.lower().split())
        t = set(text.lower().split())
        if not q:
            return 0.0
        return len(q & t) / len(q)

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
    ) -> list[KnowledgeSearchResultView]:
        if limit <= 0:
            return []

        query_embedding = await embed_text(query)
        query_embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        project_uuid = ensure_uuid(project_id)

        async with self.pool.acquire() as conn:
            vector_results = await conn.fetch(
                """
                SELECT
                    kb.id,
                    kb.content,
                    kb.document_id,
                    d.file_name AS source,
                    d.status AS document_status,
                    (1 - (kb.embedding <=> $1)) AS score
                FROM knowledge_base AS kb
                LEFT JOIN knowledge_documents AS d ON d.id = kb.document_id
                WHERE kb.project_id = $2
                  AND (d.status = 'processed' OR d.status IS NULL)
                ORDER BY kb.embedding <=> $1
                LIMIT $3
                """,
                query_embedding_str,
                project_uuid,
                limit * 2,
            )

            vector_items: list[KnowledgeSearchResultView] = [
                KnowledgeSearchResultView(
                    id=str(row["id"]),
                    content=str(row["content"]),
                    score=float(row["score"]),
                    method="vector",
                    document_id=_optional_row_text(row, "document_id"),
                    source=_optional_row_text(row, "source"),
                    document_status=_optional_row_text(row, "document_status"),
                )
                for row in vector_results
            ]

            if not hybrid_fallback:
                return vector_items[:limit]

            fts_results = await conn.fetch(
                """
                SELECT
                    kb.id,
                    kb.content,
                    kb.document_id,
                    d.file_name AS source,
                    d.status AS document_status,
                    ts_rank_cd(kb.tsv, plainto_tsquery('russian', $1)) AS score
                FROM knowledge_base AS kb
                LEFT JOIN knowledge_documents AS d ON d.id = kb.document_id
                WHERE kb.project_id = $2
                  AND (d.status = 'processed' OR d.status IS NULL)
                  AND kb.tsv @@ plainto_tsquery('russian', $1)
                ORDER BY score DESC
                LIMIT $3
                """,
                query,
                project_uuid,
                limit * 2,
            )

        merged: dict[str, KnowledgeSearchResultView] = {
            item.id: item for item in vector_items
        }

        for row in fts_results:
            row_id = str(row["id"])
            row_content = str(row["content"])
            row_score = float(row["score"])
            row_document_id = _optional_row_text(row, "document_id")
            row_source = _optional_row_text(row, "source")
            row_document_status = _optional_row_text(row, "document_status")

            if row_id in merged:
                current = merged[row_id]
                merged[row_id] = KnowledgeSearchResultView(
                    id=current.id,
                    content=current.content,
                    score=current.score * 0.7 + row_score * 0.3,
                    method="hybrid",
                    document_id=current.document_id,
                    source=current.source,
                    document_status=current.document_status,
                )
            else:
                merged[row_id] = KnowledgeSearchResultView(
                    id=row_id,
                    content=row_content,
                    score=row_score * 0.8,
                    method="fts",
                    document_id=row_document_id,
                    source=row_source,
                    document_status=row_document_status,
                )

        results = [
            KnowledgeSearchResultView(
                id=item.id,
                content=item.content,
                score=item.score + self._keyword_overlap(query, item.content) * 0.15,
                method=item.method,
                document_id=item.document_id,
                source=item.source,
                document_status=item.document_status,
            )
            for item in merged.values()
        ]

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def preview_search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[KnowledgeSearchResultView]:
        if limit <= 0:
            return []

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    kb.id,
                    kb.content,
                    kb.document_id,
                    d.file_name AS source,
                    d.status AS document_status,
                    ts_rank_cd(kb.tsv, plainto_tsquery('russian', $1)) AS score
                FROM knowledge_documents AS d
                JOIN knowledge_base AS kb ON kb.document_id = d.id
                WHERE d.project_id = $2
                  AND d.status = 'processed'
                  AND kb.tsv @@ plainto_tsquery('russian', $1)
                ORDER BY score DESC
                LIMIT $3
                """,
                query,
                ensure_uuid(project_id),
                limit,
            )

        results = [
            KnowledgeSearchResultView(
                id=str(row["id"]),
                content=str(row["content"]),
                score=float(row["score"])
                + self._keyword_overlap(query, str(row["content"])) * 0.15,
                method="fts",
                document_id=_optional_row_text(row, "document_id"),
                source=_optional_row_text(row, "source"),
                document_status=_optional_row_text(row, "document_status"),
            )
            for row in rows
        ]
        results.sort(key=lambda item: item.score, reverse=True)
        return results

    async def add_knowledge_batch(
        self,
        project_id: str,
        chunks: list[JsonObject],
        document_id: str | None = None,
    ) -> int:
        """Persist plain chunks using the legacy knowledge_base insert contract."""
        if not chunks:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for batch in _batched_chunks(
                    chunks, settings.KNOWLEDGE_EMBED_BATCH_SIZE
                ):
                    texts = [str(chunk["content"]) for chunk in batch]
                    embeddings = await embed_batch(texts)
                    for index, chunk in enumerate(batch):
                        await conn.execute(
                            """
                            INSERT INTO knowledge_base (project_id, document_id, content, embedding)
                            VALUES ($1, $2, $3, $4::vector)
                            """,
                            ensure_uuid(project_id),
                            ensure_uuid(document_id) if document_id else None,
                            str(chunk["content"]),
                            _pg_vector_text(embeddings[index]),
                        )

        return len(chunks)

    async def add_structured_knowledge_batch(
        self,
        project_id: str,
        chunks: list[JsonObject],
        document_id: str | None = None,
    ) -> int:
        """Persist LLM-normalized structured knowledge entries."""
        if not chunks:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for batch in _batched_chunks(
                    chunks, settings.KNOWLEDGE_EMBED_BATCH_SIZE
                ):
                    texts = [
                        str(chunk.get("embedding_text") or chunk["content"])
                        for chunk in batch
                    ]
                    embeddings = await embed_batch(texts)
                    for index, chunk in enumerate(batch):
                        await conn.execute(
                            """
                            INSERT INTO knowledge_base (
                                project_id,
                                document_id,
                                content,
                                embedding,
                                entry_type,
                                title,
                                source_excerpt,
                                questions,
                                synonyms,
                                tags,
                                embedding_text
                            )
                            VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11)
                            """,
                            ensure_uuid(project_id),
                            ensure_uuid(document_id) if document_id else None,
                            str(chunk["content"]),
                            _pg_vector_text(embeddings[index]),
                            str(chunk.get("entry_type") or "chunk"),
                            str(chunk["title"])
                            if chunk.get("title") is not None
                            else None,
                            str(chunk["source_excerpt"])
                            if chunk.get("source_excerpt") is not None
                            else None,
                            _jsonb_array(chunk.get("questions")),
                            _jsonb_array(chunk.get("synonyms")),
                            _jsonb_array(chunk.get("tags")),
                            str(chunk["embedding_text"])
                            if chunk.get("embedding_text") is not None
                            else None,
                        )

        return len(chunks)

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
            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_documents (project_id, file_name, file_size, uploaded_by)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """,
                ensure_uuid(project_id),
                file_name,
                file_size,
                uploaded_by,
            )

        document_id = str(row["id"])
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
            rows = await conn.fetch(
                """
                SELECT
                    d.id,
                    d.file_name,
                    d.file_size,
                    d.status,
                    d.error,
                    d.uploaded_by,
                    d.created_at,
                    d.updated_at,
                    COUNT(kb.id)::int AS chunk_count
                FROM knowledge_documents AS d
                LEFT JOIN knowledge_base AS kb ON kb.document_id = d.id
                WHERE d.project_id = $1
                GROUP BY
                    d.id,
                    d.file_name,
                    d.file_size,
                    d.status,
                    d.error,
                    d.uploaded_by,
                    d.created_at,
                    d.updated_at
                ORDER BY d.created_at DESC
                LIMIT $2 OFFSET $3
            """,
                ensure_uuid(project_id),
                limit,
                offset,
            )

        documents = [
            KnowledgeDocumentView(
                id=str(row["id"]),
                file_name=str(row["file_name"]),
                file_size=int(row["file_size"])
                if row["file_size"] is not None
                else None,
                status=str(row["status"]),
                error=str(row["error"]) if row["error"] is not None else None,
                uploaded_by=str(row["uploaded_by"])
                if row["uploaded_by"] is not None
                else None,
                created_at=_normalize_timestamp(row["created_at"]),
                updated_at=_normalize_timestamp(row["updated_at"]),
                chunk_count=int(row["chunk_count"] or 0),
            )
            for row in rows or []
        ]

        logger.debug("Retrieved knowledge documents", extra={"count": len(documents)})
        return documents

    async def get_document(
        self, document_id: str
    ) -> KnowledgeDocumentDetailView | None:
        logger.debug("Fetching knowledge document", extra={"document_id": document_id})

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, project_id, file_name, file_size, status, error, uploaded_by, created_at, updated_at
                FROM knowledge_documents
                WHERE id = $1
            """,
                ensure_uuid(document_id),
            )

            if not row:
                return None

            chunk_count = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge_base WHERE document_id = $1",
                row["id"],
            )

        return KnowledgeDocumentDetailView(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            file_name=str(row["file_name"]),
            file_size=int(row["file_size"]) if row["file_size"] is not None else None,
            status=str(row["status"]),
            error=str(row["error"]) if row["error"] is not None else None,
            uploaded_by=str(row["uploaded_by"])
            if row["uploaded_by"] is not None
            else None,
            created_at=_normalize_timestamp(row["created_at"]),
            updated_at=_normalize_timestamp(row["updated_at"]),
            chunk_count=int(chunk_count or 0),
        )

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
            await conn.execute(
                """
                UPDATE knowledge_documents
                SET status = $1, error = $2, updated_at = NOW()
                WHERE id = $3
            """,
                status,
                error,
                ensure_uuid(document_id),
            )

    async def update_document_preprocessing_status(
        self,
        document_id: str,
        *,
        mode: KnowledgePreprocessingMode,
        status: str,
        error: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_documents
                SET preprocessing_mode = $1,
                    preprocessing_status = $2,
                    preprocessing_error = $3,
                    preprocessing_model = COALESCE($4, preprocessing_model),
                    preprocessing_prompt_version = COALESCE($5, preprocessing_prompt_version),
                    preprocessing_metrics = COALESCE($6::jsonb, preprocessing_metrics),
                    updated_at = NOW()
                WHERE id = $7
                """,
                mode,
                status,
                error,
                model,
                prompt_version,
                json.dumps(metrics, ensure_ascii=False)
                if metrics is not None
                else None,
                ensure_uuid(document_id),
            )

    async def delete_document_chunks(self, document_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM knowledge_base WHERE document_id = $1",
                ensure_uuid(document_id),
            )

    async def delete_document(self, document_id: str) -> None:
        logger.info("Deleting knowledge document", extra={"document_id": document_id})

        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM knowledge_base WHERE document_id = $1",
                ensure_uuid(document_id),
            )
            await conn.execute(
                "DELETE FROM knowledge_documents WHERE id = $1",
                ensure_uuid(document_id),
            )

        logger.info("Document deleted", extra={"document_id": document_id})

    async def clear_project_knowledge(self, project_id: str) -> None:
        logger.info("Clearing knowledge base", extra={"project_id": project_id})

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM knowledge_base WHERE project_id = $1",
                    ensure_uuid(project_id),
                )
                await conn.execute(
                    "DELETE FROM knowledge_documents WHERE project_id = $1",
                    ensure_uuid(project_id),
                )

        logger.info("Knowledge base cleared", extra={"project_id": project_id})
