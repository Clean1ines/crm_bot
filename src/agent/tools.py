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

@tool
async def escalate_to_manager(project_id: str, thread_id: str, user_message: str) -> str:
    """
    Используй этот инструмент, когда пользователь требует вмешательства человека,
    выражает сильное недовольство, просит поговорить с менеджером, или вопрос выходит
    за рамки твоих компетенций. После вызова этого инструмента диалог будет передан
    оператору.
    """
    # Сам инструмент не делает ничего, кроме возврата сообщения.
    # Фактическая эскалация будет обработана в OrchestratorService.
    return "Переключаю на менеджера. Ожидайте ответа."
