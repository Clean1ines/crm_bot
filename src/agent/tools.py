from langchain_core.tools import tool
import asyncpg
import os
from src.database.repositories.knowledge_repository import KnowledgeRepository
from src.services.embedding_service import embed_text

@tool
async def search_knowledge_base(query: str, project_id: str) -> str:
    """
    Используй этот инструмент, чтобы найти информацию о компании, ценах или услугах в базе знаний.
    """
    # Устанавливаем соединение с БД (можно переиспользовать пул, но для простоты создаём новое)
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    try:
        repo = KnowledgeRepository(conn)
        results = await repo.search(project_id, query, limit=3)
        if results:
            return "\n\n".join(results)
        else:
            return "По вашему запросу ничего не найдено в базе знаний."
    finally:
        await conn.close()
