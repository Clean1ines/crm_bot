"""
Escalation node for the LangGraph pipeline.

Creates escalation side effects and returns a typed human-handoff state patch.
"""

from collections.abc import Mapping
from typing import cast

from src.agent.state import AgentState
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.thread_status import ThreadStatus
from src.domain.runtime.escalation import EscalationContext, EscalationResult
from src.domain.runtime.state_contracts import RuntimeStateInput, RuntimeStatePatch
from src.domain.runtime.tool_execution import (
    ToolExecutionOutcome,
    ToolSafeErrorCode,
    ToolExecutionStatus,
    normalize_safe_error_code,
)
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.application.ports.thread_port import ThreadLifecyclePort
from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.tools.builtins import TicketCreateTool

logger = get_logger(__name__)

MISSING_THREAD_TEXT = (
    "Escalation could not be completed because the conversation identifier is missing. "
    "Please contact support."
)

TICKET_CREATION_FAILED_TEXT = (
    "Не удалось передать обращение менеджеру из-за технической ошибки. "
    "Попробуйте ещё раз позже."
)

HANDOFF_STATE_TRANSITION_FAILED_TEXT = (
    "Не удалось завершить передачу обращения менеджеру из-за технической ошибки. "
    "Попробуйте ещё раз позже."
)


def _previous_lifecycle_from_state(state: AgentState) -> str | None:
    value = state.get("previous_lifecycle")
    if value is not None:
        text = str(value).strip()
        if text:
            return text
    return None


def _ticket_id_from_success_outcome(outcome: ToolExecutionOutcome) -> str | None:
    if outcome.status is not ToolExecutionStatus.SUCCEEDED:
        return None
    if not isinstance(outcome.payload, Mapping):
        return None
    ticket_id = str(outcome.payload.get("ticket_id") or "").strip()
    return ticket_id or None


def _escalation_failure_patch(
    *,
    state: AgentState,
    safe_error_code: str,
    response_text: str = TICKET_CREATION_FAILED_TEXT,
    ticket_id: str | None = None,
    ticket_created: bool = False,
    thread_waiting_manager: bool = False,
) -> RuntimeStatePatch:
    previous_lifecycle = _previous_lifecycle_from_state(state)
    patch = EscalationResult(
        requires_human=False,
        response_text=response_text,
    ).to_state_patch()
    patch.update(
        {
            "decision": "RESPOND",
            "requires_human": False,
            "escalation_failed": True,
            "ticket_created": ticket_created,
            "handoff_completed": False,
            "thread_waiting_manager": thread_waiting_manager,
            "notification_degraded": False,
            "tool_execution_status": ToolExecutionStatus.FAILED.value,
            "tool_execution_safe_error_code": normalize_safe_error_code(
                safe_error_code
            ),
            "cta": "none",
            "resolved_cta": None,
            "resolved_cta_reply": None,
        }
    )
    patch["handoff_ticket_id"] = ticket_id
    if previous_lifecycle is not None:
        patch["lifecycle"] = previous_lifecycle
    dialog_state = state.get("dialog_state")
    if isinstance(dialog_state, Mapping):
        next_dialog_state = dict(dialog_state)
        next_dialog_state["handoff_confirmation_pending"] = False
        next_dialog_state["last_cta"] = None
        if previous_lifecycle is not None:
            next_dialog_state["lifecycle"] = previous_lifecycle
            if next_dialog_state.get("lead_status") == "handoff_to_manager":
                next_dialog_state["lead_status"] = previous_lifecycle
        patch["dialog_state"] = next_dialog_state
    return patch


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
            result = await ticket_create_tool.run(
                args=dict(context.ticket_payload()),
                context={
                    "project_id": context.project_id,
                    "thread_id": context.thread_id,
                    "user_id": context.client_id,
                },
            )
            if result.status is not ToolExecutionStatus.SUCCEEDED:
                logger.error(
                    "Ticket creation failed; escalation aborted",
                    extra={
                        "thread_id": context.thread_id,
                        "tool_execution_status": result.status.value,
                        "safe_error_code": result.safe_error_code,
                    },
                )
                return _escalation_failure_patch(
                    state=state,
                    safe_error_code=(
                        result.safe_error_code
                        or ToolSafeErrorCode.TICKET_CREATION_FAILED.value
                    ),
                )
            ticket_id = _ticket_id_from_success_outcome(result)
            if ticket_id is None:
                logger.error(
                    "Ticket creation returned malformed success outcome; escalation aborted",
                    extra={
                        "thread_id": context.thread_id,
                        "payload_type": type(result.payload).__name__,
                    },
                )
                return _escalation_failure_patch(
                    state=state,
                    safe_error_code=ToolSafeErrorCode.INVALID_TOOL_OUTCOME.value,
                )
            logger.info(
                "Ticket created",
                extra={"ticket_id": ticket_id, "thread_id": context.thread_id},
            )
        except Exception as exc:
            logger.exception(
                "Ticket creation raised; escalation aborted",
                extra={
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "abort_escalation",
                },
            )
            return _escalation_failure_patch(
                state=state,
                safe_error_code=ToolSafeErrorCode.TICKET_CREATION_FAILED.value,
            )

        try:
            await thread_lifecycle_repo.update_status(
                context.thread_id,
                ThreadStatus.WAITING_MANAGER,
            )
        except Exception as exc:
            logger.exception(
                "Failed to move thread into waiting_manager status; escalation partial failure",
                extra={
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "ticket_id": ticket_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "partial_failure_no_ticket_compensation_available",
                },
            )
            return _escalation_failure_patch(
                state=state,
                safe_error_code=ToolSafeErrorCode.HANDOFF_STATE_TRANSITION_FAILED.value,
                response_text=HANDOFF_STATE_TRANSITION_FAILED_TEXT,
                ticket_id=ticket_id,
                ticket_created=True,
                thread_waiting_manager=False,
            )

        notification_degraded = False
        try:
            notification_payload = cast(
                JsonObject,
                {
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "message": context.user_input,
                },
            )
            await queue_repo.enqueue("notify_manager", notification_payload)
            logger.debug(
                "Manager notification enqueued", extra={"thread_id": context.thread_id}
            )
        except Exception as exc:
            notification_degraded = True
            logger.exception(
                "Manager notification failed; handoff remains active",
                extra={
                    "thread_id": context.thread_id,
                    "project_id": context.project_id,
                    "ticket_id": ticket_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "notification_best_effort_thread_waiting_manager_active",
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

        patch = EscalationResult().to_state_patch()
        patch["ticket_created"] = True
        patch["handoff_ticket_id"] = ticket_id
        patch["escalation_failed"] = False
        patch["handoff_completed"] = True
        patch["thread_waiting_manager"] = True
        patch["notification_degraded"] = notification_degraded
        logger.info(
            "Manager handoff completed",
            extra={
                "thread_id": context.thread_id,
                "ticket_id": ticket_id,
                "notification_degraded": notification_degraded,
            },
        )
        return patch

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
