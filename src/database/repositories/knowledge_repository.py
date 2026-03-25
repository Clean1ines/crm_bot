"""
Knowledge repository for RAG with hybrid search (vector + FTS + scoring fusion).
"""

import uuid
import asyncpg
from typing import List, Dict, Any, Optional

from src.core.logging import get_logger
from src.services.embedding_service import embed_text, embed_batch
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)


class KnowledgeRepository:
    def __init__(self, pool):
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
    ) -> List[Dict[str, Any]]:

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

        vector_items = [
            {
                "id": str(r["id"]),
                "content": r["content"],
                "score": float(r["score"]),
                "method": "vector",
            }
            for r in vector_results
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

        merged: Dict[str, Dict[str, Any]] = {}

        # VECTOR
        for r in vector_items:
            merged[r["id"]] = r

        # FTS fusion
        for r in fts_results:
            rid = str(r["id"])
            if rid in merged:
                merged[rid]["score"] = merged[rid]["score"] * 0.7 + float(r["score"]) * 0.3
                merged[rid]["method"] = "hybrid"
            else:
                merged[rid] = {
                    "id": rid,
                    "content": r["content"],
                    "score": float(r["score"]) * 0.8,
                    "method": "fts",
                }

        results = list(merged.values())

        # light keyword boost
        for r in results:
            r["score"] += self._keyword_overlap(query, r["content"]) * 0.15

        results.sort(key=lambda x: x["score"], reverse=True)

        return results[:limit]

    async def add_knowledge_batch(
        self,
        project_id: str,
        chunks: List[Dict[str, Any]],
        document_id: Optional[str] = None,
    ) -> int:

        if not chunks:
            return 0

        texts = [c["content"] for c in chunks]
        embeddings = await embed_batch(texts)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for i, chunk in enumerate(chunks):
                    emb_str = "[" + ",".join(str(x) for x in embeddings[i]) + "]"

                    await conn.execute(
                        """
                        INSERT INTO knowledge_base (project_id, document_id, content, embedding)
                        VALUES ($1, $2, $3, $4::vector)
                        """,
                        ensure_uuid(project_id),
                        ensure_uuid(document_id) if document_id else None,
                        chunk["content"],
                        emb_str,
                    )

        return len(chunks)

    # Document management methods

    async def create_document(
        self,
        project_id: str,
        file_name: str,
        file_size: Optional[int] = None,
        uploaded_by: Optional[str] = None,
    ) -> str:
        """
        Create a new document record.
        
        Returns:
            document_id as string.
        """
        logger.info("Creating knowledge document", extra={"project_id": project_id, "file_name": file_name})
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO knowledge_documents (project_id, file_name, file_size, uploaded_by)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, ensure_uuid(project_id), file_name, file_size, uploaded_by)
            doc_id = str(row["id"])
            logger.info("Document created", extra={"document_id": doc_id})
            return doc_id

    async def get_documents(
        self,
        project_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List documents for a project.
        """
        logger.debug("Fetching knowledge documents", extra={"project_id": project_id, "limit": limit, "offset": offset})
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, file_name, file_size, status, error, uploaded_by, created_at, updated_at
                FROM knowledge_documents
                WHERE project_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """, ensure_uuid(project_id), limit, offset)
        
        docs = []
        for row in rows:
            # Also count chunks? optional
            chunk_count = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge_base WHERE document_id = $1",
                row["id"]
            )
            doc = dict(row)
            doc["id"] = str(doc["id"])
            doc["chunk_count"] = chunk_count
            docs.append(doc)
        
        logger.debug(f"Retrieved {len(docs)} documents")
        return docs

    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single document by ID.
        """
        logger.debug("Fetching knowledge document", extra={"document_id": document_id})
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, project_id, file_name, file_size, status, error, uploaded_by, created_at, updated_at
                FROM knowledge_documents
                WHERE id = $1
            """, ensure_uuid(document_id))
            if not row:
                return None
            chunk_count = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge_base WHERE document_id = $1",
                row["id"]
            )
            doc = dict(row)
            doc["id"] = str(doc["id"])
            doc["project_id"] = str(doc["project_id"])
            doc["chunk_count"] = chunk_count
            return doc

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """
        Update document processing status.
        """
        logger.info("Updating document status", extra={"document_id": document_id, "status": status})
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE knowledge_documents
                SET status = $1, error = $2, updated_at = NOW()
                WHERE id = $3
            """, status, error, ensure_uuid(document_id))

    async def delete_document(self, document_id: str) -> None:
        """
        Delete a document and its chunks.
        """
        logger.info("Deleting knowledge document", extra={"document_id": document_id})
        async with self.pool.acquire() as conn:
            # Chunks will be deleted automatically by ON DELETE CASCADE if foreign key is set correctly,
            # but we have ON DELETE SET NULL, so we need to delete them explicitly.
            await conn.execute("DELETE FROM knowledge_base WHERE document_id = $1", ensure_uuid(document_id))
            await conn.execute("DELETE FROM knowledge_documents WHERE id = $1", ensure_uuid(document_id))
        logger.info("Document deleted", extra={"document_id": document_id})
