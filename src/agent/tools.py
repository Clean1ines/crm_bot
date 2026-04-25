"""
LangChain compatibility tools for the CRM bot agent runtime.

This module intentionally does not open DB connections, import runtime config, or
instantiate repositories. Legacy LangChain wrappers delegate execution to the
ToolRegistry, whose concrete tools are registered in the application
composition root.
"""

from typing import Any, Dict, Optional

from langchain_core.tools import tool

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# ----------------------------------------------------------------------
# Legacy global context (for backward compatibility with existing agent)
# ----------------------------------------------------------------------
_current_project_id: Optional[str] = None
_current_thread_id: Optional[str] = None


def set_current_context(project_id: str, thread_id: str) -> None:
    """
    Set project/thread context for legacy LangChain tool wrappers.

    New ToolRegistry-based flows pass context explicitly and should not rely on
    these module globals.
    """
    global _current_project_id, _current_thread_id
    _current_project_id = project_id
    _current_thread_id = thread_id
    logger.debug(
        "Context set for tools",
        extra={"project_id": project_id, "thread_id": thread_id},
    )


def _get_lazy_registry() -> Any:
    """
    Lazy import of the global ToolRegistry instance.

    Keeping the import lazy avoids import cycles while preserving compatibility
    for legacy LangChain wrappers.
    """
    from src.tools import tool_registry

    return tool_registry


def _tool_context() -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    if _current_project_id:
        context["project_id"] = _current_project_id
    if _current_thread_id:
        context["thread_id"] = _current_thread_id
    return context


def _format_knowledge_result(result: Dict[str, Any]) -> str:
    if result.get("error"):
        return str(result["error"])

    raw_results = result.get("results")
    if isinstance(raw_results, str):
        return raw_results

    if not raw_results:
        return "По вашему запросу ничего не найдено в базе знаний."

    chunks: list[str] = []
    for item in raw_results:
        if isinstance(item, dict):
            content = str(item.get("content") or "").strip()
            if content:
                chunks.append(content)
        elif item is not None:
            chunks.append(str(item))

    if not chunks:
        return "По вашему запросу ничего не найдено в базе знаний."

    return "\n\n".join(chunks)


@tool
async def search_knowledge_base(query: str) -> str:
    """
    Find information in the project knowledge base.

    Legacy LangChain-facing wrapper. Actual execution is delegated to the
    registered ``search_knowledge`` ToolRegistry tool.
    """
    if not _current_project_id:
        logger.warning("search_knowledge_base called without project context")
        return "Ошибка: контекст проекта не задан."

    logger.info(
        "Searching knowledge base via ToolRegistry",
        extra={
            "project_id": _current_project_id,
            "query_preview": query[:50],
        },
    )

    try:
        result = await _get_lazy_registry().execute(
            "search_knowledge",
            {"query": query, "limit": 3},
            _tool_context(),
        )
        return _format_knowledge_result(result)
    except Exception as exc:
        logger.error(
            "Knowledge base search failed",
            extra={
                "project_id": _current_project_id,
                "query": query,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        return "Произошла ошибка при поиске в базе знаний."


@tool
async def escalate_to_manager() -> str:
    """
    Escalate the current conversation to a human manager.

    Legacy LangChain-facing wrapper. Actual execution is delegated to the
    registered ``escalate_to_manager`` ToolRegistry tool.
    """
    if not _current_project_id or not _current_thread_id:
        logger.warning(
            "escalate_to_manager called without required context",
            extra={"project_id": _current_project_id, "thread_id": _current_thread_id},
        )
        return "Ошибка: контекст проекта или диалога не задан."

    logger.info(
        "Escalation requested via ToolRegistry",
        extra={
            "project_id": _current_project_id,
            "thread_id": _current_thread_id,
        },
    )

    try:
        result = await _get_lazy_registry().execute(
            "escalate_to_manager",
            {
                "reason": "User requested human assistance",
                "priority": "normal",
            },
            _tool_context(),
        )
        return str(result.get("message") or "Переключаю на менеджера. Ожидайте ответа.")
    except Exception as exc:
        logger.error(
            "Escalation failed",
            extra={
                "project_id": _current_project_id,
                "thread_id": _current_thread_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        return "Не удалось переключить на менеджера. Попробуйте позже."


# ----------------------------------------------------------------------
# Tool-registry compatible wrappers for older dynamic call sites
# ----------------------------------------------------------------------

async def search_knowledge_via_registry(
    args: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Backward-compatible wrapper for dynamic execution.

    Delegates to the registered ``search_knowledge`` tool without touching DB
    or runtime config from the agent layer.
    """
    project_id = context.get("project_id")
    query = str(args.get("query", "")).strip()

    if not project_id:
        logger.error("search_knowledge_via_registry called without project_id")
        return {"error": "project_id required in context"}

    if not query:
        logger.error("search_knowledge_via_registry called without query")
        return {"error": "query required"}

    logger.debug(
        "Executing knowledge search via registry",
        extra={"project_id": project_id, "query_preview": query[:50]},
    )

    registry_args = dict(args)
    registry_args["query"] = query
    return await _get_lazy_registry().execute("search_knowledge", registry_args, context)


async def escalate_via_registry(
    args: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Backward-compatible wrapper for escalation dynamic execution.

    Delegates to the registered ``escalate_to_manager`` tool without direct DB
    access from the agent layer.
    """
    project_id = context.get("project_id")
    thread_id = context.get("thread_id")

    if not project_id or not thread_id:
        logger.error(
            "escalate_via_registry called without required context",
            extra={"project_id": project_id, "thread_id": thread_id},
        )
        return {"error": "project_id and thread_id required in context"}

    logger.info(
        "Executing escalation via registry",
        extra={"project_id": project_id, "thread_id": thread_id},
    )

    registry_args = dict(args)
    registry_args.setdefault("reason", "User requested human assistance")
    registry_args.setdefault("priority", "normal")
    return await _get_lazy_registry().execute("escalate_to_manager", registry_args, context)
