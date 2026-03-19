import uuid
from typing import List, Dict, Any
from src.services.embedding_service import embed_text
from src.core.logging import get_logger

logger = get_logger(__name__)


class KnowledgeRepository:
    def __init__(self, conn):
        self.conn = conn

    async def search(self, project_id: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        # 1. Векторный поиск (все результаты, без отсечения по порогу)
        query_emb = await embed_text(query)
        emb_str = '[' + ','.join(str(x) for x in query_emb) + ']'
        vector_rows = await self.conn.fetch("""
            SELECT content, (embedding <=> $2::vector) as distance
            FROM knowledge_base
            WHERE project_id = $1
            ORDER BY embedding <=> $2::vector
            LIMIT $3
        """, uuid.UUID(project_id), emb_str, limit)

        results = []
        for row in vector_rows:
            score = 1 - row["distance"]  # Преобразуем расстояние в схожесть
            results.append({
                "content": row["content"],
                "score": score,
                "method": "vector"
            })

        # 2. Если векторных результатов меньше запрошенного лимита,
        # дополняем полнотекстовым поиском
        if len(results) < limit:
            fts_rows = await self.conn.fetch("""
                SELECT content, ts_rank(tsv, plainto_tsquery('russian', $2)) as rank
                FROM knowledge_base
                WHERE project_id = $1 AND tsv @@ plainto_tsquery('russian', $2)
                ORDER BY rank DESC
                LIMIT $3
            """, uuid.UUID(project_id), query, limit - len(results))
            for row in fts_rows:
                results.append({
                    "content": row["content"],
                    "score": row["rank"],
                    "method": "fts"
                })

        logger.info(f"Search returned {len(results)} results (vector: {sum(1 for r in results if r['method']=='vector')}, fts: {sum(1 for r in results if r['method']=='fts')})")
        return results
