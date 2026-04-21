"""
Persist node for LangGraph pipeline.

Saves assistant message and state to the database, emits events for auditing,
stores dialog_state in long-term memory, and updates analytics columns.
"""

import datetime
from typing import Any, Dict, Optional

from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.event_repository import EventRepository
from src.database.repositories.memory_repository import MemoryRepository
from src.database.repositories.queue_repository import QueueRepository
from src.database.models import ThreadStatus
from src.agent.utils import coerce_int

logger = get_logger(__name__)




def _infer_topic_from_intent(intent: Optional[str]) -> Optional[str]:
    """
    Infer a stable topic from the current intent.

    Args:
        intent: Current intent label.

    Returns:
        Canonical topic or None.
    """
    value = (intent or "").strip().lower()
    mapping = {
        "ask_price": "pricing",
        "ask_features": "product",
        "ask_integration": "integration",
        "pricing": "pricing",
        "sales": "product",
        "support": "support",
        "feedback": "feedback",
        "handoff_request": "handoff",
        "angry": "angry",
    }
    return mapping.get(value)


def _normalize_dialog_state(state: AgentState) -> Dict[str, Any]:
    """
    Build a dialog_state snapshot from the current agent state.

    Args:
        state: Current agent state.

    Returns:
        Normalized dialog_state dictionary.
    """
    existing = state.get("dialog_state")
    if not isinstance(existing, dict):
        existing = {}

    dialog_state = {
        "last_intent": existing.get("last_intent") or state.get("intent"),
        "last_cta": existing.get("last_cta") or state.get("cta"),
        "last_topic": existing.get("last_topic") or state.get("topic") or _infer_topic_from_intent(state.get("intent")),
        "repeat_count": coerce_int(existing.get("repeat_count"), 0),
        "lead_status": existing.get("lead_status") or state.get("lead_status") or state.get("lifecycle") or "active_client",
        "lifecycle": state.get("lifecycle") or existing.get("lifecycle") or state.get("lead_status") or "active_client",
    }

    if dialog_state["repeat_count"] <= 0 and dialog_state["last_intent"]:
        dialog_state["repeat_count"] = 1

    return dialog_state


def _extract_dialog_state_from_memory(state: AgentState) -> Dict[str, Any]:
    """
    Extract dialog_state from user_memory if it already exists there.

    Args:
        state: Current agent state.

    Returns:
        Dialog state dictionary or an empty dict.
    """
    user_memory = state.get("user_memory") or {}
    items = user_memory.get("dialog_state") or []

    for item in items:
        if not isinstance(item, dict):
            continue

        value = item.get("value")
        if isinstance(value, dict):
            return value

    return {}


def create_persist_node(
    thread_repo: ThreadRepository,
    event_repo: Optional[EventRepository] = None,
    memory_repo: Optional[MemoryRepository] = None,
    summarizer: Optional[Any] = None,
    queue_repo: Optional[QueueRepository] = None,
):
    """
    Factory function that creates a persist node with injected dependencies.

    Args:
        thread_repo: ThreadRepository instance for saving messages and state.
        event_repo: Optional EventRepository for emitting events.
        memory_repo: Optional MemoryRepository for storing user memory.
        summarizer: Optional SummarizerService for background summarization.
        queue_repo: Optional QueueRepository for enqueuing metrics updates.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        (usually empty on success).
    """
    async def _persist_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Persist conversation data and emit events.

        Expected state fields:
          - thread_id: str
          - project_id: str
          - response_text: str
          - tool_name: optional
          - tool_args: optional
          - requires_human: bool
          - client_id: optional
          - intent, lifecycle, cta, decision: optional for analytics
          - dialog_state: optional for long-term dialog memory
          - close_ticket: optional boolean to indicate closing the thread

        Returns:
            Empty dict on success, or {"error": ...} on failure.
        """
        thread_id = state.get("thread_id")
        project_id = state.get("project_id")
        response_text = state.get("response_text")
        user_input = (state.get("user_input") or "").lower()
        client_id = state.get("client_id")
        close_ticket = state.get("close_ticket", False)

        if not thread_id or not project_id:
            logger.error("persist_node missing required identifiers")
            return {"error": "Missing thread_id or project_id"}

        # 1. Save assistant message.
        if response_text:
            try:
                await thread_repo.add_message(
                    thread_id,
                    role="assistant",
                    content=response_text,
                )
                logger.debug("Assistant message saved", extra={"thread_id": thread_id})
            except Exception:
                logger.exception("Failed to save assistant message", extra={"thread_id": thread_id})
                # Continue to save state anyway.

        # 2. Save state snapshot.
        try:
            state_copy = dict(state)
            state_copy.pop("messages", None)
            state_copy.pop("history", None)
            state_copy.pop("knowledge_chunks", None)

            await thread_repo.save_state_json(thread_id, state_copy)
            logger.debug("State JSON saved", extra={"thread_id": thread_id})
        except Exception:
            logger.exception("Failed to save state_json", extra={"thread_id": thread_id})

        # 3. Emit events.
        if event_repo:
            try:
                await event_repo.append(
                    stream_id=thread_id,
                    project_id=project_id,
                    event_type="ai_response",
                    payload={
                        "text": response_text,
                        "confidence": state.get("confidence"),
                        "requires_human": state.get("requires_human", False),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Failed to emit ai_response event",
                    extra={"thread_id": thread_id, "error": str(exc)},
                )

            tool_name = state.get("tool_name")
            if tool_name:
                try:
                    await event_repo.append(
                        stream_id=thread_id,
                        project_id=project_id,
                        event_type="tool_called",
                        payload={
                            "tool": tool_name,
                            "args": state.get("tool_args"),
                            "result": state.get("tool_result"),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to emit tool_called event",
                        extra={"thread_id": thread_id, "error": str(exc)},
                    )

            if state.get("requires_human"):
                try:
                    await event_repo.append(
                        stream_id=thread_id,
                        project_id=project_id,
                        event_type="ticket_created",
                        payload={
                            "reason": "Human escalation requested",
                            "manager_notified": True,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to emit ticket_created event",
                        extra={"thread_id": thread_id, "error": str(exc)},
                    )

        # 4. Store memory.
        if memory_repo and client_id:
            try:
                # Preserve and refresh dialog_state in long-term memory.
                dialog_state = _normalize_dialog_state(state)
                memory_dialog_state = _extract_dialog_state_from_memory(state)
                if memory_dialog_state:
                    # Merge any previously stored values with the current snapshot.
                    merged_dialog_state = dict(memory_dialog_state)
                    merged_dialog_state.update(dialog_state)
                    dialog_state = merged_dialog_state

                await memory_repo.set(
                    project_id=project_id,
                    client_id=client_id,
                    key="dialog_state",
                    value=dialog_state,
                    type_="dialog_state",
                )
                logger.debug(
                    "Dialog state stored",
                    extra={
                        "project_id": project_id,
                        "client_id": client_id,
                        "repeat_count": dialog_state.get("repeat_count"),
                        "lead_status": dialog_state.get("lead_status"),
                    },
                )

                lifecycle_stage = dialog_state.get("lifecycle") or dialog_state.get("lead_status")
                if lifecycle_stage:
                    await memory_repo.set(
                        project_id=project_id,
                        client_id=client_id,
                        key="stage",
                        value={"stage": lifecycle_stage},
                        type_="lifecycle",
                    )
                    logger.debug(
                        "Lifecycle stored",
                        extra={
                            "project_id": project_id,
                            "client_id": client_id,
                            "lifecycle": lifecycle_stage,
                        },
                    )

                # Lightweight backward-compatible signals.
                if user_input:
                    if "не хочу звонок" in user_input:
                        await memory_repo.set(
                            project_id=project_id,
                            client_id=client_id,
                            key="calls",
                            value=False,
                            type_="rejection",
                        )
                        logger.debug("Stored rejection memory: no calls")

                    if any(phrase in user_input for phrase in ["дорого", "слишком дорого"]):
                        await memory_repo.set(
                            project_id=project_id,
                            client_id=client_id,
                            key="price_sensitivity",
                            value="high",
                            type_="behavior",
                        )
                        logger.debug("Stored price sensitivity memory")

                    business_phrases = ["у меня салон", "мой бизнес", "я из"]
                    for phrase in business_phrases:
                        if phrase in user_input:
                            await memory_repo.set(
                                project_id=project_id,
                                client_id=client_id,
                                key="business_type",
                                value="salon",
                                type_="context",
                            )
                            logger.debug("Stored business context")
                            break

                    issue_keywords = ["не работает", "бесит", "ошибка", "жалоба"]
                    if any(kw in user_input for kw in issue_keywords):
                        await memory_repo.set(
                            project_id=project_id,
                            client_id=client_id,
                            key="last_issue",
                            value=user_input[:200],
                            type_="issues",
                        )
                        logger.debug("Stored issue memory")

            except Exception:
                logger.exception("Failed to store user memory", extra={"client_id": client_id})

        # 5. Update analytics fields in threads table.
        try:
            await thread_repo.update_analytics(
                thread_id=thread_id,
                intent=state.get("intent"),
                lifecycle=state.get("lifecycle"),
                cta=state.get("cta"),
                decision=state.get("decision"),
            )
            logger.debug("Analytics updated", extra={"thread_id": thread_id})
        except Exception as exc:
            logger.warning(
                "Failed to update analytics",
                extra={"thread_id": thread_id, "error": str(exc)},
            )

        # 6. Handle thread closure and metrics update
        if close_ticket and queue_repo:
            try:
                # Get message counts
                counts = await thread_repo.get_message_counts(thread_id)
                # Get thread creation time
                thread_info = await thread_repo.get_thread_with_project(thread_id)
                if thread_info:
                    created_at = thread_info.get("created_at")
                    if created_at:
                        resolution_time = (datetime.datetime.utcnow() - created_at).total_seconds()
                    else:
                        resolution_time = None
                else:
                    resolution_time = None
                
                await queue_repo.enqueue(
                    task_type="update_metrics",
                    payload={
                        "thread_id": thread_id,
                        "total_messages": counts["total"],
                        "ai_messages": counts["ai"],
                        "manager_messages": counts["manager"],
                        "resolution_time": resolution_time,
                        "close_ticket": True
                    }
                )
                logger.debug("Metrics update enqueued for closed thread", extra={"thread_id": thread_id})
            except Exception as exc:
                logger.warning(
                    "Failed to enqueue metrics update",
                    extra={"thread_id": thread_id, "error": str(exc)},
                )

        # 7. Trigger summarization (placeholder).
        # if summarizer and condition_met:
        #     asyncio.create_task(summarizer.summarize_and_save(thread_id))

        return {}

    def _get_persist_input_size(state: AgentState) -> int:
        """
        Estimate persist node input size.

        Args:
            state: Current agent state.

        Returns:
            Zero, because this is a side-effect node.
        """
        return 0

    def _get_persist_output_size(result: Dict[str, Any]) -> int:
        """
        Estimate persist node output size.

        Args:
            result: Node result.

        Returns:
            Zero, because this node returns no meaningful payload.
        """
        return 0

    async def persist_node(state: AgentState) -> Dict[str, Any]:
        """
        Execute persist node with execution tracing.

        Args:
            state: Current agent state.

        Returns:
            Dictionary of state updates.
        """
        return await log_node_execution(
            "persist",
            _persist_node_impl,
            state,
            get_input_size=_get_persist_input_size,
            get_output_size=_get_persist_output_size,
        )

    return persist_node
