"""
LangChain tools for the CRM bot.
Provides search over knowledge base and escalation to manager.
"""

from langchain_core.tools import tool
import asyncpg
from src.core.config import settings
from src.core.logging import get_logger
from src.database.repositories.knowledge_repository import KnowledgeRepository
from src.services.embedding_service import embed_text

logger = get_logger(__name__)

# Глобальные переменные для передачи контекста из графа
_current_project_id = None
_current_thread_id = None

def set_current_context(project_id: str, thread_id: str):
    """Устанавливает текущие project_id и thread_id для использования в инструментах."""
    global _current_project_id, _current_thread_id
    _current_project_id = project_id
    _current_thread_id = thread_id

@tool
async def search_knowledge_base(query: str) -> str:
    """
    Use this tool to find information about the company, pricing, or services in the knowledge base.
    """
    global _current_project_id
    if not _current_project_id:
        return "Ошибка: контекст проекта не задан."
    logger.info(f"Searching knowledge base for query: {query[:50]}... (project {_current_project_id})")
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        repo = KnowledgeRepository(conn)
        results = await repo.search(_current_project_id, query, limit=3)
        if results:
            logger.debug(f"Found {len(results)} results")
            return "\n\n".join(results)
        else:
            logger.debug("No results found")
            return "По вашему запросу ничего не найдено в базе знаний."
    except Exception as e:
        logger.error(f"Knowledge base search failed: {e}")
        return "Произошла ошибка при поиске в базе знаний."
    finally:
        await conn.close()

@tool
async def escalate_to_manager() -> str:
    """
    Use this tool when the user requests human intervention, expresses strong dissatisfaction,
    asks to speak with a manager, or the question is outside your competence.
    After calling this tool, the conversation will be handed over to an operator.
    """
    logger.info("Escalation requested")
    return "Переключаю на менеджера. Ожидайте ответа."
