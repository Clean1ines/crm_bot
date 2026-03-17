"""
LangChain tools for the CRM bot.

This module provides both legacy function-based tools for backward compatibility
and Tool-registry-compatible wrappers for dynamic execution from canvas workflows.

Tools:
- search_knowledge_base: RAG search over project knowledge base
- escalate_to_manager: Create ticket and notify human manager

For new workflows, use tool_registry.execute() instead of direct calls.
"""

import asyncpg
from typing import Any, Dict, Optional

from langchain_core.tools import tool

from src.core.config import settings
from src.core.logging import get_logger
from src.database.repositories.knowledge_repository import KnowledgeRepository
from src.services.embedding_service import embed_text

logger = get_logger(__name__)

# ----------------------------------------------------------------------
# Legacy global context (for backward compatibility with existing agent)
# ----------------------------------------------------------------------
_current_project_id: Optional[str] = None
_current_thread_id: Optional[str] = None


def set_current_context(project_id: str, thread_id: str) -> None:
    """
    Устанавливает текущие project_id и thread_id для использования в инструментах.
    
    This is used by the legacy agent flow to pass context to tools.
    For new Tool-registry-based flows, context is passed explicitly via dict.
    
    Args:
        project_id: UUID of the project.
        thread_id: UUID of the conversation thread.
    """
    global _current_project_id, _current_thread_id
    _current_project_id = project_id
    _current_thread_id = thread_id
    logger.debug(
        "Context set for tools",
        extra={"project_id": project_id, "thread_id": thread_id}
    )


@tool
async def search_knowledge_base(query: str) -> str:
    """
    Use this tool to find information about the company, pricing, or services in the knowledge base.
    
    Args:
        query: Natural language search query.
    
    Returns:
        Formatted search results or error message.
    """
    global _current_project_id
    
    if not _current_project_id:
        logger.warning("search_knowledge_base called without project context")
        return "Ошибка: контекст проекта не задан."
    
    logger.info(
        "Searching knowledge base",
        extra={
            "project_id": _current_project_id,
            "query_preview": query[:50]
        }
    )
    
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        repo = KnowledgeRepository(conn)
        results = await repo.search(_current_project_id, query, limit=3)
        
        if results:
            logger.debug(
                "Knowledge search found results",
                extra={"project_id": _current_project_id, "count": len(results)}
            )
            return "\n\n".join(results)
        else:
            logger.debug(
                "Knowledge search returned no results",
                extra={"project_id": _current_project_id, "query": query}
            )
            return "По вашему запросу ничего не найдено в базе знаний."
            
    except Exception as e:
        logger.error(
            "Knowledge base search failed",
            extra={
                "project_id": _current_project_id,
                "query": query,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return "Произошла ошибка при поиске в базе знаний."
    finally:
        await conn.close()


@tool
async def escalate_to_manager() -> str:
    """
    Use this tool when the user requests human intervention, expresses strong dissatisfaction,
    asks to speak with a manager, or the question is outside your competence.
    After calling this tool, the conversation will be handed over to an operator.
    
    Returns:
        Confirmation message.
    """
    logger.info(
        "Escalation requested",
        extra={
            "project_id": _current_project_id,
            "thread_id": _current_thread_id
        }
    )
    return "Переключаю на менеджера. Ожидайте ответа."


# ----------------------------------------------------------------------
# Tool-registry compatible wrappers (for dynamic execution)
# These are used by canvas workflows via tool_registry.execute()
# ----------------------------------------------------------------------

def _get_lazy_registry():
    """
    Lazy import of tool_registry to avoid circular dependencies.
    
    Returns:
        ToolRegistry instance from src.tools.
    """
    from src.tools import tool_registry
    return tool_registry


async def search_knowledge_via_registry(
    args: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Wrapper for search_knowledge_base that works with ToolRegistry.
    
    Args:
        args: Tool arguments with 'query' key.
        context: Must contain 'project_id' for multi-tenant isolation.
    
    Returns:
        Dict with search results.
    """
    project_id = context.get("project_id")
    query = args.get("query", "")
    
    if not project_id:
        logger.error("search_knowledge_via_registry called without project_id")
        return {"error": "project_id required in context"}
    
    logger.debug(
        "Executing knowledge search via registry",
        extra={"project_id": project_id, "query_preview": query[:50]}
    )
    
    # Use legacy function with context set
    set_current_context(project_id, context.get("thread_id", ""))
    result = await search_knowledge_base.func(query)  # type: ignore
    
    return {
        "results": result,
        "query": query,
        "project_id": project_id
    }


async def escalate_via_registry(
    args: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Wrapper for escalate_to_manager that works with ToolRegistry.
    
    Args:
        args: Tool arguments (currently unused).
        context: Must contain 'project_id' and 'thread_id'.
    
    Returns:
        Dict with escalation confirmation.
    """
    project_id = context.get("project_id")
    thread_id = context.get("thread_id")
    
    if not project_id or not thread_id:
        logger.error(
            "escalate_via_registry called without required context",
            extra={"project_id": project_id, "thread_id": thread_id}
        )
        return {"error": "project_id and thread_id required in context"}
    
    logger.info(
        "Executing escalation via registry",
        extra={"project_id": project_id, "thread_id": thread_id}
    )
    
    # Use legacy function with context set
    set_current_context(project_id, thread_id)
    result = await escalate_to_manager.func()  # type: ignore
    
    return {
        "escalated": True,
        "project_id": project_id,
        "thread_id": thread_id,
        "message": result
    }
