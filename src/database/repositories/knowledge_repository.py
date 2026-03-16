import uuid
from typing import List, Optional
from src.services.embedding_service import embed_text
from src.core.logging import get_logger

logger = get_logger(__name__)

class KnowledgeRepository:
    def __init__(self, conn):
        """
        Принимает объект соединения с БД (asyncpg).
        """
        self.conn = conn

    async def search(self, project_id: str, query: str, limit: int = 5) -> List[str]:
        """
        Ищет релевантные фрагменты в базе знаний проекта.
        Возвращает список текстов.
        """
        logger.info(f"Searching knowledge base for project {project_id}", extra={"query": query, "limit": limit})
        # Генерируем эмбеддинг запроса
        query_emb = await embed_text(query)
        # Преобразуем в строку для PostgreSQL
        emb_str = '[' + ','.join(str(x) for x in query_emb) + ']'

        # Выполняем векторный поиск
        rows = await self.conn.fetch("""
            SELECT content
            FROM knowledge_base
            WHERE project_id = $1
            ORDER BY embedding <=> $2::vector
            LIMIT $3
        """, uuid.UUID(project_id), emb_str, limit)

        results = [row['content'] for row in rows]
        logger.info(f"Found {len(results)} results for project {project_id}")
        return results
