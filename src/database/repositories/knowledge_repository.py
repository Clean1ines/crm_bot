"""
Knowledge repository for RAG with hybrid search (vector + FTS + scoring fusion).
"""

import uuid
import asyncpg
from typing import List, Dict, Any

from src.core.logging import get_logger
from src.services.embedding_service import embed_text, embed_batch

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
                uuid.UUID(project_id),
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
                uuid.UUID(project_id),
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
                        INSERT INTO knowledge_base (project_id, content, embedding)
                        VALUES ($1, $2, $3::vector)
                        """,
                        uuid.UUID(project_id),
                        chunk["content"],
                        emb_str,
                    )

        return len(chunks)