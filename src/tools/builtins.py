"""
Built-in tools for the MRAK-OS platform.

This module provides wrapper implementations of core platform functionality
as Tool instances that can be registered in the ToolRegistry:
- SearchKnowledgeTool: RAG search over project knowledge base
- EscalateTool: Create ticket and notify managers

These tools wrap existing repository functions while conforming to the
Tool interface for dynamic execution from canvas workflows.
"""

from typing import Any, Dict, Optional

from src.core.logging import get_logger
from src.tools.registry import Tool, ToolExecutionError

logger = get_logger(__name__)


class SearchKnowledgeTool(Tool):
    """
    Tool for searching project knowledge base using RAG.
    
    This tool wraps the knowledge_repository.search() function
    and provides semantic search over embedded documents.
    
    Usage in canvas:
    {
        "type": "tool_call",
        "tool_name": "search_knowledge",
        "args": {"query": "What is your return policy?"}
    }
    
    Context required:
    - project_id: UUID of the project to search within
    
    Returns:
    {
        "results": [
            {"content": "...", "score": 0.95, "source": "faq.txt"},
            ...
        ],
        "query": "original query"
    }
    """
    
    name = "search_knowledge"
    description = "Search project knowledge base using semantic RAG. Use this to find information about the company, pricing, services, or policies."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query in natural language",
                "minLength": 1,
                "maxLength": 500
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "minimum": 1,
                "maximum": 10,
                "default": 5
            },
            "category": {
                "type": "string",
                "description": "Optional category filter (e.g., 'faq', 'pricing')",
                "enum": ["faq", "pricing", "docs", "policies", "general"]
            }
        },
        "required": ["query"],
        "additionalProperties": False
    }
    
    def __init__(self, knowledge_repository) -> None:
        """
        Initialize the SearchKnowledgeTool with a knowledge repository.
        
        Args:
            knowledge_repository: Instance of KnowledgeRepository for search.
        """
        self._repo = knowledge_repository
        logger.debug("SearchKnowledgeTool initialized")
    
    async def run(self, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute semantic search over the project's knowledge base.
        
        Args:
            args: Tool arguments with 'query' (required), 'limit', 'category'.
            context: Must contain 'project_id' for multi-tenant isolation.
        
        Returns:
            Dict with search results and metadata.
        
        Raises:
            ToolExecutionError: If search fails or project not found.
        """
        project_id = self._require_context_field(context, "project_id")
        query = args.get("query", "").strip()
        limit = min(args.get("limit", 5), 10)  # Cap at 10 for safety
        category = args.get("category")
        
        if not query:
            raise ToolExecutionError(
                self.name,
                "Search query cannot be empty",
                {"args": args}
            )
        
        logger.debug(
            "Executing knowledge search",
            extra={
                "project_id": project_id,
                "query_preview": query[:50],
                "limit": limit,
                "category": category
            }
        )
        
        try:
            # Call the underlying repository search
            results = await self._repo.search(
                project_id=str(project_id),
                query=query,
                limit=limit,
                category=category
            )
            
            # Format results for canvas/agent consumption
            formatted_results = [
                {
                    "content": r.get("content", ""),
                    "score": float(r.get("score", 0.0)),
                    "source": r.get("source"),
                    "title": r.get("title"),
                    "chunk_index": r.get("chunk_index")
                }
                for r in results
            ]
            
            logger.debug(
                "Knowledge search completed",
                extra={
                    "project_id": project_id,
                    "results_count": len(formatted_results)
                }
            )
            
            return {
                "results": formatted_results,
                "query": query,
                "total_found": len(formatted_results)
            }
            
        except Exception as e:
            logger.error(
                "Knowledge search failed",
                extra={
                    "project_id": project_id,
                    "query": query,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            raise ToolExecutionError(
                self.name,
                f"Search failed: {str(e)}",
                {"project_id": project_id, "query": query}
            )


class EscalateTool(Tool):
    """
    Tool for escalating a conversation to a human manager.
    
    This tool creates a ticket and notifies managers via the execution queue.
    It wraps the existing escalation logic while providing a clean interface
    for canvas workflows.
    
    Usage in canvas:
    {
        "type": "tool_call",
        "tool_name": "escalate_to_manager",
        "args": {"reason": "Customer requested human help"}
    }
    
    Context required:
    - project_id: UUID of the project
    - thread_id: UUID of the conversation thread to escalate
    
    Returns:
    {
        "ticket_created": true,
        "ticket_id": "uuid-string",
        "managers_notified": 3
    }
    """
    
    name = "escalate_to_manager"
    description = "Escalate the conversation to a human manager. Use this when the user requests human help, expresses strong dissatisfaction, or when AI cannot answer the question."
    input_schema = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Reason for escalation (will be shown to manager)",
                "minLength": 1,
                "maxLength": 500
            },
            "priority": {
                "type": "string",
                "description": "Optional priority level",
                "enum": ["low", "normal", "high", "urgent"],
                "default": "normal"
            }
        },
        "required": ["reason"],
        "additionalProperties": False
    }
    
    def __init__(
        self,
        thread_repository,
        queue_repository,
        project_repository
    ) -> None:
        """
        Initialize the EscalateTool with required repositories.
        
        Args:
            thread_repository: ThreadRepository for status updates.
            queue_repository: QueueRepository for notification tasks.
            project_repository: ProjectRepository for manager lookup.
        """
        self._thread_repo = thread_repository
        self._queue_repo = queue_repository
        self._project_repo = project_repository
        logger.debug("EscalateTool initialized")
    
    async def run(self, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a ticket and notify managers for the escalated conversation.
        
        Args:
            args: Tool arguments with 'reason' (required), 'priority'.
            context: Must contain 'project_id' and 'thread_id'.
        
        Returns:
            Dict with ticket confirmation and notification status.
        
        Raises:
            ToolExecutionError: If escalation fails.
        """
        project_id = self._require_context_field(context, "project_id")
        thread_id = self._require_context_field(context, "thread_id")
        
        reason = args.get("reason", "User requested human assistance").strip()
        priority = args.get("priority", "normal")
        
        if not reason:
            raise ToolExecutionError(
                self.name,
                "Escalation reason cannot be empty",
                {"args": args}
            )
        
        logger.info(
            "Executing escalation",
            extra={
                "project_id": project_id,
                "thread_id": thread_id,
                "reason_preview": reason[:50],
                "priority": priority
            }
        )
        
        try:
            # Update thread status to MANUAL
            await self._thread_repo.update_status(
                thread_id=str(thread_id),
                status="manual"
            )
            
            # Get managers for this project
            managers = await self._project_repo.get_managers(str(project_id))
            
            if not managers:
                logger.warning(
                    "Escalation: no managers configured",
                    extra={"project_id": project_id, "thread_id": thread_id}
                )
                # Still mark as escalated, but note no notification sent
                return {
                    "ticket_created": True,
                    "thread_id": str(thread_id),
                    "managers_notified": 0,
                    "warning": "No managers configured for this project"
                }
            
            # Queue notification task for each manager
            notification_payload = {
                "thread_id": str(thread_id),
                "project_id": str(project_id),
                "reason": reason,
                "priority": priority,
                "escalated_at": context.get("timestamp")
            }
            
            job_id = await self._queue_repo.enqueue(
                task_type="notify_manager",
                payload=notification_payload
            )
            
            logger.info(
                "Escalation completed",
                extra={
                    "thread_id": thread_id,
                    "managers_count": len(managers),
                    "queue_job_id": job_id
                }
            )
            
            return {
                "ticket_created": True,
                "thread_id": str(thread_id),
                "managers_notified": len(managers),
                "queue_job_id": job_id,
                "priority": priority
            }
            
        except Exception as e:
            logger.error(
                "Escalation failed",
                extra={
                    "project_id": project_id,
                    "thread_id": thread_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            raise ToolExecutionError(
                self.name,
                f"Escalation failed: {str(e)}",
                {"project_id": project_id, "thread_id": thread_id}
            )
