"""
Escalation node for the LangGraph pipeline.

Creates escalation side effects and returns a typed human-handoff state patch.
"""

from typing import cast

from src.agent.state import AgentState
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.thread_status import ThreadStatus
from src.domain.runtime.escalation import EscalationContext, EscalationResult
from src.domain.runtime.state_contracts import RuntimeStateInput, RuntimeStatePatch
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.application.ports.thread_port import ThreadLifecyclePort
from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.tools.builtins import TicketCreateTool

logger = get_logger(__name__)

MISSING_THREAD_TEXT = (
    "Escalation could not be completed because the conversation identifier is missing. "
    "Please contact support."
)


def create_escalate_node(
    thread_lifecycle_repo: ThreadLifecyclePort,
    queue_repo: QueueRepository,
    ticket_create_tool: TicketCreateTool,
):
    """
    Create the escalation node with injected dependencies.
    """

    async def _escalate_node_impl(state: AgentState) -> RuntimeStatePatch:
        context = EscalationContext.from_state(cast(RuntimeStateInput, state))
        if not context.thread_id:
            logger.error("escalate_node called with no thread_id")
            return EscalationResult(response_text=MISSING_THREAD_TEXT).to_state_patch()

        logger.info(
            "Escalating thread",
            extra={
                "thread_id": context.thread_id,
                "project_id": context.project_id,
                "user_input": context.user_input[:50],
            },
        )

        try:
            await thread_lifecycle_repo.update_status(
                context.thread_id,
                ThreadStatus.WAITING_MANAGER,
            )
        except Exception as exc:
            logger.exception(
                "Failed to move thread into waiting_manager status",
                extra={
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "degrade_continue",
                },
            )

        try:
            result = await ticket_create_tool.run(
                args=dict(context.ticket_payload()),
                context={
                    "project_id": context.project_id,
                    "thread_id": context.thread_id,
                    "user_id": context.client_id,
                },
            )
            logger.info(
                "Ticket created",
                extra={
                    "ticket_id": result.get("ticket_id"),
                    "thread_id": context.thread_id,
                },
            )
        except Exception as exc:
            logger.exception(
                "Failed to create ticket",
                extra={
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "degrade_continue",
                },
            )

        try:
            notification_payload = cast(
                JsonObject,
                {
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "message": context.user_input[:200],
                },
            )
            await queue_repo.enqueue("notify_manager", notification_payload)
            logger.debug(
                "Manager notification enqueued", extra={"thread_id": context.thread_id}
            )
        except Exception as exc:
            logger.exception(
                "Failed to enqueue manager notification",
                extra={
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "degrade_continue",
                },
            )

        try:
            await queue_repo.enqueue(
                "update_metrics",
                {"thread_id": context.thread_id, "escalated": True},
            )
            logger.debug(
                "Metrics update enqueued", extra={"thread_id": context.thread_id}
            )
        except Exception as exc:
            logger.exception(
                "Failed to enqueue metrics update",
                extra={
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "degrade_continue",
                },
            )

        return EscalationResult().to_state_patch()

    def _get_escalate_input_size(state: AgentState) -> int:
        return len(str(state.get("user_input") or ""))

    def _get_escalate_output_size(result: RuntimeStatePatch) -> int:
        return len(str(result.get("response_text") or ""))

    async def escalate_node(state: AgentState) -> RuntimeStatePatch:
        return await log_node_execution(
            "escalate",
            _escalate_node_impl,
            state,
            get_input_size=_get_escalate_input_size,
            get_output_size=_get_escalate_output_size,
        )

    return escalate_node
