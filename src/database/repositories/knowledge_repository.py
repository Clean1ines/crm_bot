"""
Knowledge repository for RAG with hybrid search.
"""

import uuid
import asyncpg
from typing import List, Dict, Any, Optional

from src.core.logging import get_logger
from src.services.embedding_service import embed_text

logger = get_logger(__name__)


class KnowledgeRepository:
    def __init__(self, pool):
        self.pool = pool

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 5,
        hybrid_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge base using vector similarity, optionally augmented with FTS.

        Args:
            project_id: Project UUID.
            query: Search query.
            limit: Maximum number of results.
            hybrid_fallback: If True and vector results are insufficient, add FTS results.

        Returns:
            List of dicts with keys: content, score, method (vector or fts), id.
        """
        # Generate embedding for the query
        query_embedding = await embed_text(query)

        # Vector search
        async with self.pool.acquire() as conn:
            vector_results = await conn.fetch(
                """
                SELECT id, content, 1 - (embedding <=> $1) as score
                FROM knowledge_base
                WHERE project_id = $2
                ORDER BY embedding <=> $1
                LIMIT $3
                """,
                query_embedding,
                uuid.UUID(project_id),
                limit,
            )

        vector_items = [
            {
                "id": str(r["id"]),
                "content": r["content"],
                "score": r["score"],
                "method": "vector",
            }
            for r in vector_results
        ]

        # If we already have enough results, return them
        if len(vector_items) >= limit or not hybrid_fallback:
            return vector_items[:limit]

        # Otherwise, augment with FTS
        fts_limit = limit - len(vector_items)
        async with self.pool.acquire() as conn:
            fts_results = await conn.fetch(
                """
                SELECT id, content, ts_rank_cd(tsv, plainto_tsquery('russian', $1)) as score
                FROM knowledge_base
                WHERE project_id = $2
                  AND tsv @@ plainto_tsquery('russian', $1)
                ORDER BY score DESC
                LIMIT $3
                """,
                query,
                uuid.UUID(project_id),
                fts_limit,
            )

        # Merge, avoid duplicates (by id)
        seen_ids = {r["id"] for r in vector_items}
        for r in fts_results:
            rid = str(r["id"])
            if rid not in seen_ids:
                vector_items.append(
                    {
                        "id": rid,
                        "content": r["content"],
                        "score": r["score"],
                        "method": "fts",
                    }
                )
                seen_ids.add(rid)

        return vector_items[:limit]

    async def add_knowledge_batch(
        self,
        project_id: str,
        chunks: List[Dict[str, Any]],
    ) -> int:
        """
        Add multiple knowledge chunks with embeddings.

        Args:
            project_id: Project UUID.
            chunks: List of dicts with keys: content (required), optionally metadata.

        Returns:
            Number of inserted rows.
        """
        if not chunks:
            return 0

        from src.services.embedding_service import embed_batch
        texts = [c["content"] for c in chunks]
        embeddings = await embed_batch(texts)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for i, chunk in enumerate(chunks):
                    await conn.execute(
                        """
                        INSERT INTO knowledge_base (project_id, content, embedding)
                        VALUES ($1, $2, $3)
                        """,
                        uuid.UUID(project_id),
                        chunk["content"],
                        embeddings[i],
                    )
        logger.info(f"Added {len(chunks)} knowledge chunks for project {project_id}")
        return len(chunks)
