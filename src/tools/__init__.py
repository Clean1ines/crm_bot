"""
Tool Registry package for MRAK-OS.

This package provides the core tool execution infrastructure:
- Tool ABC: Interface all tools must implement
- ToolRegistry: Singleton for registering and executing tools
- Built-in tools: SearchKnowledgeTool, EscalateTool
- Extension tools: HTTPTool, N8NTool (for Marketplace)

Usage:
    from src.tools import tool_registry, SearchKnowledgeTool
    
    # Register a tool (typically done in lifespan.py)
    tool_registry.register(SearchKnowledgeTool(knowledge_repo))
    
    # Execute a tool from agent or workflow
    result = await tool_registry.execute(
        "search_knowledge",
        {"query": "What are your hours?"},
        {"project_id": "...", "thread_id": "..."}
    )
"""

from src.core.logging import get_logger
from src.tools.registry import Tool, ToolRegistry, ToolExecutionError, tool_registry

logger = get_logger(__name__)

# Re-export core classes for convenience
__all__ = [
    "Tool",
    "ToolRegistry", 
    "ToolExecutionError",
    "tool_registry",
    "SearchKnowledgeTool",
    "EscalateTool",
    "HTTPTool",
    "N8NTool",
]

# Lazy import built-in tools to avoid circular dependencies
def _register_builtin_tools(
    knowledge_repo=None,
    thread_repo=None,
    queue_repo=None,
    project_repo=None
) -> None:
    """
    Register built-in tools in the global registry.
    
    This function should be called during application startup
    (e.g., in lifespan.py) after repositories are initialized.
    
    Args:
        knowledge_repo: KnowledgeRepository instance for search tool.
        thread_repo: ThreadRepository instance for escalation tool.
        queue_repo: QueueRepository instance for escalation tool.
        project_repo: ProjectRepository instance for escalation tool.
    """
    if knowledge_repo:
        from src.tools.builtins import SearchKnowledgeTool
        tool_registry.register(SearchKnowledgeTool(knowledge_repo))
        logger.info("Registered SearchKnowledgeTool")
    
    if thread_repo and queue_repo and project_repo:
        from src.tools.builtins import EscalateTool
        tool_registry.register(EscalateTool(
            thread_repository=thread_repo,
            queue_repository=queue_repo,
            project_repository=project_repo
        ))
        logger.info("Registered EscalateTool")
    
    # Register extension tools (always available)
    from src.tools.http_tool import HTTPTool
    tool_registry.register(HTTPTool())
    logger.info("Registered HTTPTool")
    
    from src.tools.n8n_tool import N8NTool
    tool_registry.register(N8NTool())
    logger.info("Registered N8NTool")


# Convenience function for getting all tool metadata
def get_tool_catalog(public_only: bool = False) -> list[dict]:
    """
    Get a catalog of registered tools for canvas UI or API docs.
    
    Args:
        public_only: If True, only return tools marked as public.
    
    Returns:
        List of dicts with tool metadata.
    """
    return tool_registry.list_tools(public_only=public_only)


# Export the singleton instance
__singleton__ = tool_registry
