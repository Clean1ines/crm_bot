"""
Persist node for the LangGraph pipeline.

Stores state snapshots, analytics, memory signals, and side-effect events after
the graph finishes processing a turn.
"""

import datetime

from src.agent.state import AgentState
from src.domain.runtime.persistence import PersistenceContext
from src.infrastructure.db.repositories.event_repository import EventRepository
from src.infrastructure.db.repositories.memory_repository import MemoryRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.thread.messages import ThreadMessageRepository
from src.infrastructure.db.repositories.thread.runtime_state import ThreadRuntimeStateRepository
from src.infrastructure.db.repositories.thread.read import ThreadReadRepository
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)


def create_persist_node(
    thread_message_repo: ThreadMessageRepository,
    thread_runtime_state_repo: ThreadRuntimeStateRepository,
    thread_read_repo: ThreadReadRepository,
    event_repo: EventRepository | None = None,
    memory_repo: MemoryRepository | None = None,
    summarizer: object | None = None,
    queue_repo: QueueRepository | None = None,
):
    """
    Create the persist node with injected repositories.
    """

    async def _persist_node_impl(state: AgentState) -> dict[str, object]:
        context = PersistenceContext.from_state(state)
        if not context.thread_id or not context.project_id:
            logger.error("persist_node missing required identifiers")
            return {"error": "Missing thread_id or project_id"}

        if context.response_text:
            try:
                await thread_message_repo.add_message(
                    context.thread_id,
                    role="assistant",
                    content=context.response_text,
                )
                logger.debug("Assistant message saved", extra={"thread_id": context.thread_id})
            except Exception as exc:
                logger.exception(
                    "Failed to save assistant message",
                    extra={
                        "thread_id": context.thread_id,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "policy": "degrade_continue",
                    },
                )

        try:
            await thread_runtime_state_repo.save_state_json(context.thread_id, context.state_payload or {})
            logger.debug("State JSON saved", extra={"thread_id": context.thread_id})
        except Exception as exc:
            logger.exception(
                "Failed to save state_json",
                extra={
                    "thread_id": context.thread_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "degrade_continue",
                },
            )

        if event_repo:
            try:
                await event_repo.append(
                    stream_id=context.thread_id,
                    project_id=context.project_id,
                    event_type="ai_response",
                    payload={
                        "text": context.response_text,
                        "confidence": context.confidence,
                        "requires_human": context.requires_human,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Failed to emit ai_response event",
                    extra={"thread_id": context.thread_id, "error": str(exc)},
                )

            if context.tool_name:
                try:
                    await event_repo.append(
                        stream_id=context.thread_id,
                        project_id=context.project_id,
                        event_type="tool_called",
                        payload={
                            "tool": context.tool_name,
                            "args": context.tool_args,
                            "result": context.tool_result,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to emit tool_called event",
                        extra={"thread_id": context.thread_id, "error": str(exc)},
                    )

            if context.requires_human:
                try:
                    await event_repo.append(
                        stream_id=context.thread_id,
                        project_id=context.project_id,
                        event_type="ticket_created",
                        payload={"reason": "Human escalation requested", "manager_notified": True},
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to emit ticket_created event",
                        extra={"thread_id": context.thread_id, "error": str(exc)},
                    )

        if memory_repo and context.client_id:
            try:
                dialog_state = context.normalized_dialog_state()
                await memory_repo.set(
                    project_id=context.project_id,
                    client_id=context.client_id,
                    key="dialog_state",
                    value=dialog_state,
                    type_="dialog_state",
                )

                lifecycle_stage = dialog_state.get("lifecycle") or dialog_state.get("lead_status")
                if lifecycle_stage:
                    await memory_repo.set(
                        project_id=context.project_id,
                        client_id=context.client_id,
                        key="stage",
                        value={"stage": lifecycle_stage},
                        type_="lifecycle",
                    )

                if context.user_input:
                    if "не хочу звонок" in context.user_input:
                        await memory_repo.set(
                            project_id=context.project_id,
                            client_id=context.client_id,
                            key="calls",
                            value=False,
                            type_="rejection",
                        )

                    if any(phrase in context.user_input for phrase in ["дорого", "слишком дорого"]):
                        await memory_repo.set(
                            project_id=context.project_id,
                            client_id=context.client_id,
                            key="price_sensitivity",
                            value="high",
                            type_="behavior",
                        )

                    if any(phrase in context.user_input for phrase in ["у меня салон", "мой бизнес", "я из"]):
                        await memory_repo.set(
                            project_id=context.project_id,
                            client_id=context.client_id,
                            key="business_type",
                            value="salon",
                            type_="context",
                        )

                    if any(kw in context.user_input for kw in ["не работает", "бесит", "ошибка", "жалоба"]):
                        await memory_repo.set(
                            project_id=context.project_id,
                            client_id=context.client_id,
                            key="last_issue",
                            value=context.user_input[:200],
                            type_="issues",
                        )
            except Exception as exc:
                logger.exception(
                    "Failed to store user memory",
                    extra={
                        "client_id": context.client_id,
                        "project_id": context.project_id,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "policy": "degrade_continue",
                    },
                )

        try:
            await thread_runtime_state_repo.update_analytics(
                thread_id=context.thread_id,
                intent=context.intent,
                lifecycle=context.lifecycle,
                cta=context.cta,
                decision=context.decision,
            )
            logger.debug("Analytics updated", extra={"thread_id": context.thread_id})
        except Exception as exc:
            logger.warning(
                "Failed to update analytics",
                extra={"thread_id": context.thread_id, "error": str(exc)},
            )

        if context.close_ticket and queue_repo:
            try:
                counts = await thread_message_repo.get_message_counts_view(context.thread_id)
                total_messages = counts.total
                ai_messages = counts.ai
                manager_messages = counts.manager

                thread_info = await thread_read_repo.get_thread_with_project_view(context.thread_id)
                created_at = thread_info.created_at if thread_info else None
                resolution_time = None
                if created_at:
                    resolution_time = (
                        datetime.datetime.now(datetime.UTC) - created_at.astimezone(datetime.UTC)
                    ).total_seconds()

                await queue_repo.enqueue(
                    task_type="update_metrics",
                    payload={
                        "thread_id": context.thread_id,
                        "total_messages": total_messages,
                        "ai_messages": ai_messages,
                        "manager_messages": manager_messages,
                        "resolution_time": resolution_time,
                        "close_ticket": True,
                    },
                )
                logger.debug(
                    "Metrics update enqueued for closed thread",
                    extra={"thread_id": context.thread_id},
                )
            except Exception as exc:
                logger.warning(
                    "Failed to enqueue metrics update",
                    extra={"thread_id": context.thread_id, "error": str(exc)},
                )

        # summarizer remains intentionally deferred until its contract is cleaned too
        _ = summarizer
        return {}

    def _get_persist_input_size(state: AgentState) -> int:
        return 0

    def _get_persist_output_size(result: dict[str, object]) -> int:
        return 0

    async def persist_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "persist",
            _persist_node_impl,
            state,
            get_input_size=_get_persist_input_size,
            get_output_size=_get_persist_output_size,
        )

    return persist_node
