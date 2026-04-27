"""
Built-in tools for the MRAK-OS platform.

This module provides wrapper implementations of core platform functionality
as Tool instances that can be registered in the ToolRegistry:
- SearchKnowledgeTool: RAG search over project knowledge base
- EscalateTool: Create ticket and notify managers

These tools wrap existing repository functions while conforming to the
Tool interface for dynamic execution from agent tool calls.
"""

import httpx

from src.infrastructure.logging.logger import get_logger
from src.tools.registry import Tool, ToolExecutionError
from src.infrastructure.llm.rag_service import RAGService

logger = get_logger(__name__)


def _as_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_int(value: object, default: int = 5) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return default
        try:
            return int(normalized)
        except ValueError:
            return default
    return default


def _as_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return default
        try:
            return float(normalized)
        except ValueError:
            return default
    return default


class SearchKnowledgeTool(Tool):
    """
    Tool for searching project knowledge base using RAG.

    This tool wraps the RAGService which provides:
    - Query normalization
    - Query expansion via LLM (Groq)
    - Multi-query vector + FTS search
    - Result merging and ranking

    Usage:
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
                "maxLength": 500,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "minimum": 1,
                "maximum": 10,
                "default": 5,
            },
            "category": {
                "type": "string",
                "description": "Optional category filter (e.g., 'faq', 'pricing')",
                "enum": ["faq", "pricing", "docs", "policies", "general"],
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, rag_service: RAGService) -> None:
        """
        Initialize the SearchKnowledgeTool with a RAG service.

        Args:
            rag_service: RAGService instance for enhanced search.
        """
        self._rag_service = rag_service
        logger.debug("SearchKnowledgeTool initialized")

    async def run(
        self, args: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
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
        query = _as_text(args.get("query")).strip()
        limit = min(_as_int(args.get("limit"), 5), 10)  # Cap at 10 for safety
        # category is currently not used by repository; ignore it
        # category = args.get("category")

        if not query:
            raise ToolExecutionError(
                self.name, "Search query cannot be empty", {"args": args}
            )

        logger.debug(
            "Executing knowledge search",
            extra={
                "project_id": project_id,
                "query_preview": query[:50],
                "limit": limit,
            },
        )

        try:
            # Use RAGService with expansion
            results = await self._rag_service.search_with_expansion(
                project_id=str(project_id), query=query, final_limit=limit
            )

            # Format results for agent consumption
            formatted_results = [
                {
                    "id": r.get("id"),
                    "content": r.get("content", ""),
                    "score": _as_float(r.get("score"), 0.0),
                    "method": r.get("method"),
                    "source": r.get("source"),
                    "title": r.get("title"),
                    "chunk_index": r.get("chunk_index"),
                }
                for r in results
            ]

            logger.debug(
                "Knowledge search completed",
                extra={
                    "project_id": project_id,
                    "results_count": len(formatted_results),
                },
            )

            return {
                "results": formatted_results,
                "query": query,
                "total_found": len(formatted_results),
            }

        except Exception as e:
            logger.error(
                "Knowledge search failed",
                extra={
                    "project_id": project_id,
                    "query": query,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise ToolExecutionError(
                self.name,
                f"Search failed: {str(e)}",
                {"project_id": project_id, "query": query},
            )


class EscalateTool(Tool):
    """
    Tool for escalating a conversation to a human manager.

    This tool creates a ticket and notifies managers via the execution queue.
    It wraps the existing escalation logic while providing a clean interface
    for agent tool calls.

    Usage:
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
                "maxLength": 500,
            },
            "priority": {
                "type": "string",
                "description": "Optional priority level",
                "enum": ["low", "normal", "high", "urgent"],
                "default": "normal",
            },
        },
        "required": ["reason"],
        "additionalProperties": False,
    }

    def __init__(
        self, thread_lifecycle_repo, queue_repository, project_members
    ) -> None:
        """
        Initialize the EscalateTool with required repositories.

        Args:
            thread_lifecycle_repo: Thread lifecycle repository for status updates.
            queue_repository: QueueRepository for notification tasks.
            project_members: ProjectMemberRepository for manager lookup.
        """
        self._thread_lifecycle_repo = thread_lifecycle_repo
        self._queue_repo = queue_repository
        self._project_members = project_members
        logger.debug("EscalateTool initialized")

    async def run(
        self, args: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
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

        reason = _as_text(args.get("reason"), "User requested human assistance").strip()
        priority = args.get("priority", "normal")

        if not reason:
            raise ToolExecutionError(
                self.name, "Escalation reason cannot be empty", {"args": args}
            )

        logger.info(
            "Executing escalation",
            extra={
                "project_id": project_id,
                "thread_id": thread_id,
                "reason_preview": reason[:50],
                "priority": priority,
            },
        )

        try:
            # Update thread status to MANUAL
            await self._thread_lifecycle_repo.update_status(
                thread_id=str(thread_id), status="manual"
            )

            # Get managers for this project
            managers = await self._project_members.get_manager_notification_targets(
                str(project_id)
            )

            if not managers:
                logger.warning(
                    "Escalation: no managers configured",
                    extra={"project_id": project_id, "thread_id": thread_id},
                )
                # Still mark as escalated, but note no notification sent
                return {
                    "ticket_created": True,
                    "thread_id": str(thread_id),
                    "managers_notified": 0,
                    "warning": "No managers configured for this project",
                }

            # Queue notification task for each manager
            notification_payload = {
                "thread_id": str(thread_id),
                "project_id": str(project_id),
                "reason": reason,
                "priority": priority,
                "escalated_at": context.get("timestamp"),
            }

            job_id = await self._queue_repo.enqueue(
                task_type="notify_manager", payload=notification_payload
            )

            logger.info(
                "Escalation completed",
                extra={
                    "thread_id": thread_id,
                    "managers_count": len(managers),
                    "queue_job_id": job_id,
                },
            )

            return {
                "ticket_created": True,
                "thread_id": str(thread_id),
                "managers_notified": len(managers),
                "queue_job_id": job_id,
                "priority": priority,
            }

        except Exception as e:
            logger.error(
                "Escalation failed",
                extra={
                    "project_id": project_id,
                    "thread_id": thread_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise ToolExecutionError(
                self.name,
                f"Escalation failed: {str(e)}",
                {"project_id": project_id, "thread_id": thread_id},
            )


class CRMGetUserTool(Tool):
    """
    Tool to retrieve project-scoped contact information from the CRM by telegram_id or email.

    Usage:
    {
        "tool": "crm.get_user",
        "args": {"telegram_id": 123456789}
    }
    or
    {
        "tool": "crm.get_user",
        "args": {"email": "user@example.com"}
    }

    Context required:
    - project_id: UUID of the project.

    Returns:
    {
        "found": true,
        "user": {
            "id": "uuid",
            "user_id": "optional-platform-user-uuid",
            "telegram_id": 123456789,
            "username": "john_doe",
            "full_name": "John Doe",
            "email": "john@example.com",
            "company": "Acme Inc",
            "phone": "+1234567890",
            "metadata": {}
        }
    }
    or {"found": false, "user": null}
    """

    name = "crm.get_user"
    description = (
        "Retrieve project-scoped CRM contact information by telegram_id or email."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "telegram_id": {"type": "integer", "description": "Telegram chat ID"},
            "email": {
                "type": "string",
                "format": "email",
                "description": "Email address",
            },
        },
        "oneOf": [{"required": ["telegram_id"]}, {"required": ["email"]}],
        "additionalProperties": False,
    }

    def __init__(self, pool):
        self._pool = pool
        logger.debug("CRMGetUserTool initialized")

    async def run(
        self, args: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        project_id = self._require_context_field(context, "project_id")

        telegram_id = args.get("telegram_id")
        email = args.get("email")

        async with self._pool.acquire() as conn:
            if telegram_id:
                row = await conn.fetchrow(
                    """
                    SELECT
                        id,
                        user_id,
                        chat_id AS telegram_id,
                        username,
                        full_name,
                        email,
                        company,
                        phone,
                        metadata
                    FROM clients
                    WHERE project_id = $1 AND chat_id = $2
                    """,
                    project_id,
                    str(telegram_id),
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT
                        id,
                        user_id,
                        chat_id AS telegram_id,
                        username,
                        full_name,
                        email,
                        company,
                        phone,
                        metadata
                    FROM clients
                    WHERE project_id = $1 AND email = $2
                    """,
                    project_id,
                    email,
                )

        if not row:
            return {"found": False, "user": None}

        user = dict(row)
        user["id"] = str(user["id"])  # UUID to string
        user["user_id"] = str(user["user_id"]) if user.get("user_id") else None
        return {"found": True, "user": user}


class CRMCreateUserTool(Tool):
    """
    Tool to create a new project-scoped contact record in the CRM (clients table).

    Usage:
    {
        "tool": "crm.create_user",
        "args": {
            "telegram_id": 123456789,
            "username": "john_doe",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "company": "Acme Inc",
            "phone": "+1234567890",
            "metadata": {"industry": "ecommerce"}
        }
    }

    Context required:
    - project_id: UUID of the project.

    Returns:
    {
        "success": true,
        "client_id": "uuid"
    }
    """

    name = "crm.create_user"
    description = "Create a new project-scoped CRM contact/lead."
    input_schema = {
        "type": "object",
        "properties": {
            "telegram_id": {"type": "integer", "description": "Telegram chat ID"},
            "username": {"type": "string", "description": "Telegram username"},
            "first_name": {"type": "string", "description": "First name"},
            "last_name": {"type": "string", "description": "Last name"},
            "email": {
                "type": "string",
                "format": "email",
                "description": "Email address",
            },
            "company": {"type": "string", "description": "Company name"},
            "phone": {"type": "string", "description": "Phone number"},
            "metadata": {"type": "object", "description": "Additional metadata"},
        },
        "required": ["telegram_id"],
        "additionalProperties": False,
    }

    def __init__(self, pool):
        self._pool = pool
        logger.debug("CRMCreateUserTool initialized")

    async def run(
        self, args: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        project_id = self._require_context_field(context, "project_id")

        telegram_id = args["telegram_id"]
        username = args.get("username")
        first_name = args.get("first_name", "")
        last_name = args.get("last_name", "")
        full_name = (
            f"{first_name} {last_name}".strip() if first_name or last_name else None
        )
        email = args.get("email")
        company = args.get("company")
        phone = args.get("phone")
        metadata = args.get("metadata", {})

        async with self._pool.acquire() as conn:
            # Check if contact already exists inside this project context.
            existing = await conn.fetchval(
                "SELECT id FROM clients WHERE project_id = $1 AND chat_id = $2",
                project_id,
                str(telegram_id),
            )
            if existing:
                return {
                    "success": False,
                    "error": "Contact already exists",
                    "client_id": str(existing),
                    "user_id": str(existing),
                }

            client_id = await conn.fetchval(
                """
                INSERT INTO clients (
                    project_id,
                    chat_id,
                    username,
                    full_name,
                    email,
                    company,
                    phone,
                    metadata,
                    source
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'tool')
                RETURNING id
            """,
                project_id,
                str(telegram_id),
                username,
                full_name,
                email,
                company,
                phone,
                metadata,
            )

            return {
                "success": True,
                "client_id": str(client_id),
                "user_id": str(client_id),
            }


class CRMCollectProfileTool(Tool):
    """
    Tool that returns a list of fields to collect during onboarding.
    Does not write to database; used for orchestration.

    Usage:
    {
        "tool": "crm.collect_profile",
        "args": {"stage": "onboarding_step_1"}
    }

    Returns:
    {
        "asking_fields": ["company_name", "industry", "monthly_orders", "crm_used", "api_keys_needed"]
    }
    """

    name = "crm.collect_profile"
    description = "Return list of profile fields to collect from user."
    input_schema = {
        "type": "object",
        "properties": {"stage": {"type": "string", "description": "Onboarding stage"}},
        "additionalProperties": False,
    }

    def __init__(self):
        logger.debug("CRMCollectProfileTool initialized")

    async def run(
        self, args: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        # For now, return static list
        return {
            "asking_fields": [
                "company_name",
                "industry",
                "monthly_orders",
                "crm_used",
                "api_keys_needed",
            ]
        }


class TicketCreateTool(Tool):
    """
    Tool to create a support ticket/task in the tasks table.

    Usage:
    {
        "tool": "ticket.create",
        "args": {
            "title": "Request: custom integration",
            "description": "User requests Postgres + OAuth",
            "priority": "high"
        }
    }

    Context required:
    - project_id: UUID
    - thread_id: UUID (optional but recommended)
    - user_id: UUID (client id from threads)

    Returns:
    {
        "ticket_id": "uuid",
        "status": "open"
    }
    """

    name = "ticket.create"
    description = "Create a support ticket/task for managers."
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title", "maxLength": 255},
            "description": {"type": "string", "description": "Detailed description"},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "default": "medium",
            },
        },
        "required": ["title"],
        "additionalProperties": False,
    }

    def __init__(self, pool):
        self._pool = pool
        logger.debug("TicketCreateTool initialized")

    async def run(
        self, args: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        project_id = self._require_context_field(context, "project_id")
        thread_id = context.get("thread_id")
        user_id = context.get("user_id")  # client UUID

        title = args["title"]
        description = args.get("description", "")
        priority = args.get("priority", "medium")

        async with self._pool.acquire() as conn:
            ticket_id = await conn.fetchval(
                """
                INSERT INTO tasks (project_id, thread_id, client_id, title, description, priority, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'open')
                RETURNING id
            """,
                project_id,
                thread_id,
                user_id,
                title,
                description,
                priority,
            )

            return {"ticket_id": str(ticket_id), "status": "open"}


class TelegramSendMessageTool(Tool):
    """
    Tool to send a message via the project's bot using Telegram API.

    Usage:
    {
        "tool": "telegram.send_message",
        "args": {
            "chat_id": 123456789,
            "text": "Hello, world!",
            "parse_mode": "Markdown"
        }
    }

    Context required:
    - project_id: UUID (to fetch bot token)

    Returns:
    {
        "ok": true,
        "message_id": 12345
    }
    """

    name = "telegram.send_message"
    description = "Send a message to a Telegram user via the project's bot."
    input_schema = {
        "type": "object",
        "properties": {
            "chat_id": {"type": "integer", "description": "Telegram chat ID"},
            "text": {"type": "string", "description": "Message text"},
            "parse_mode": {
                "type": "string",
                "enum": ["Markdown", "HTML"],
                "default": "Markdown",
            },
        },
        "required": ["chat_id", "text"],
        "additionalProperties": False,
    }

    def __init__(self, project_tokens):
        self._project_tokens = project_tokens
        logger.debug("TelegramSendMessageTool initialized")

    async def run(
        self, args: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        project_id = self._require_context_field(context, "project_id")

        chat_id = args["chat_id"]
        text = args["text"]
        parse_mode = args.get("parse_mode")  # default None, we handle manually

        # Fetch bot token
        bot_token = await self._project_tokens.get_bot_token(project_id)
        if not bot_token:
            raise ToolExecutionError(self.name, "No bot token configured for project")

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                error_data = resp.json()
                raise ToolExecutionError(
                    self.name,
                    f"Telegram API error: {error_data.get('description', 'Unknown error')}",
                )
            result = resp.json()
            return {
                "ok": result.get("ok", False),
                "message_id": result.get("result", {}).get("message_id"),
            }
