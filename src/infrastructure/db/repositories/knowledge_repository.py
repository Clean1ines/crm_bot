"""
Knowledge repository for RAG with hybrid search.

Clean Architecture contract:
- DB rows are converted to explicit typed read views inside this repository.
- Repository read methods do not return dict/Mapping compatibility objects.
"""

from uuid import UUID

import asyncpg

from src.domain.project_plane.knowledge_views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentView,
    KnowledgeSearchResultView,
)
from src.infrastructure.llm.embedding_service import embed_batch, embed_text
from src.infrastructure.logging.logger import get_logger
from src.utils.uuid_utils import ensure_uuid


logger = get_logger(__name__)


def _normalize_timestamp(value: object) -> object:
    """
    Keep test strings unchanged and serialize real datetime-like values only
    when the repository owns the DB-row normalization boundary.
    """
    if value is not None and hasattr(value, "isoformat"):
        return value.isoformat()
    return value


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
        query_embedding = await embed_text(query)
        query_embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        async with self.pool.acquire() as conn:
            vector_results = await conn.fetch(
                """
                SELECT id, content, (1 - (embedding <=> $1)) AS score
                FROM knowledge_base
                WHERE project_id = $2
                ORDER BY embedding <=> $1
                LIMIT $3
                """,
                query_embedding_str,
                ensure_uuid(project_id),
                limit * 2,
            )

        vector_items: list[KnowledgeSearchResultView] = [
            KnowledgeSearchResultView(
                id=str(row["id"]),
                content=str(row["content"]),
                score=float(row["score"]),
                method="vector",
            )
            for row in vector_results
        ]

        if not hybrid_fallback:
            return vector_items[:limit]

        async with self.pool.acquire() as conn:
            fts_results = await conn.fetch(
                """
                SELECT id, content,
                       ts_rank_cd(tsv, plainto_tsquery('russian', $1)) AS score
                FROM knowledge_base
                WHERE project_id = $2
                  AND tsv @@ plainto_tsquery('russian', $1)
                ORDER BY score DESC
                LIMIT $3
                """,
                query,
                ensure_uuid(project_id),
                limit * 2,
            )

        merged: dict[str, KnowledgeSearchResultView] = {
            item.id: item for item in vector_items
        }

        for row in fts_results:
            row_id = str(row["id"])
            row_content = str(row["content"])
            row_score = float(row["score"])

            if row_id in merged:
                current = merged[row_id]
                merged[row_id] = KnowledgeSearchResultView(
                    id=current.id,
                    content=current.content,
                    score=current.score * 0.7 + row_score * 0.3,
                    method="hybrid",
                )
            else:
                merged[row_id] = KnowledgeSearchResultView(
                    id=row_id,
                    content=row_content,
                    score=row_score * 0.8,
                    method="fts",
                )

        results = [
            KnowledgeSearchResultView(
                id=item.id,
                content=item.content,
                score=item.score + self._keyword_overlap(query, item.content) * 0.15,
                method=item.method,
            )
            for item in merged.values()
        ]

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def add_knowledge_batch(
        self,
        project_id: str,
        chunks: list[dict[str, object]],
        document_id: str | None = None,
    ) -> int:
        if not chunks:
            return 0

        texts = [str(chunk["content"]) for chunk in chunks]
        embeddings = await embed_batch(texts)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for index, chunk in enumerate(chunks):
                    embedding = embeddings[index]
                    embedding_as_pg_vector = "[" + ",".join(str(x) for x in embedding) + "]"

                    await conn.execute(
                        """
                        INSERT INTO knowledge_base (project_id, document_id, content, embedding)
                        VALUES ($1, $2, $3, $4::vector)
                        """,
                        ensure_uuid(project_id),
                        ensure_uuid(document_id) if document_id else None,
                        str(chunk["content"]),
                        embedding_as_pg_vector,
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
                SELECT id, file_name, file_size, status, error, uploaded_by, created_at, updated_at
                FROM knowledge_documents
                WHERE project_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """,
                ensure_uuid(project_id),
                limit,
                offset,
            )

            documents: list[KnowledgeDocumentView] = []
            for row in rows or []:
                chunk_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM knowledge_base WHERE document_id = $1",
                    row["id"],
                )

                documents.append(
                    KnowledgeDocumentView(
                        id=str(row["id"]),
                        file_name=str(row["file_name"]),
                        file_size=int(row["file_size"]) if row["file_size"] is not None else None,
                        status=str(row["status"]),
                        error=str(row["error"]) if row["error"] is not None else None,
                        uploaded_by=str(row["uploaded_by"]) if row["uploaded_by"] is not None else None,
                        created_at=_normalize_timestamp(row["created_at"]),
                        updated_at=_normalize_timestamp(row["updated_at"]),
                        chunk_count=int(chunk_count or 0),
                    )
                )

        logger.debug("Retrieved knowledge documents", extra={"count": len(documents)})
        return documents

    async def get_document(self, document_id: str) -> KnowledgeDocumentDetailView | None:
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
            uploaded_by=str(row["uploaded_by"]) if row["uploaded_by"] is not None else None,
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
