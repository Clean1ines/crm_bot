"""
Persist node for LangGraph pipeline.

Saves assistant message and state to the database, and emits events
for auditing and analytics.
"""

from typing import Dict, Any, Optional

from src.core.logging import get_logger
from src.agent.state import AgentState
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.event_repository import EventRepository

logger = get_logger(__name__)


def create_persist_node(
    thread_repo: ThreadRepository,
    event_repo: Optional[EventRepository] = None,
    summarizer: Optional[Any] = None  # placeholder for summarizer service
):
    """
    Factory function that creates a persist node with injected dependencies.

    Args:
        thread_repo: ThreadRepository instance for saving messages and state.
        event_repo: Optional EventRepository for emitting events.
        summarizer: Optional SummarizerService for background summarization.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        (usually empty on success).
    """
    async def persist_node(state: AgentState) -> Dict[str, Any]:
        """
        Persist conversation data and emit events.

        Expected state fields:
          - thread_id: str
          - project_id: str
          - response_text: str (final answer)
          - tool_name: optional, if tool was called
          - tool_args: optional
          - requires_human: bool, if escalation happened
          - (optionally) tool_result, etc.

        Actions:
          1. Save assistant message to messages table.
          2. Save state_json to threads table.
          3. Emit events:
             - ai_response (always)
             - tool_called (if tool was used)
             - ticket_created (if escalation happened)
          4. Trigger background summarization if needed (placeholder).

        Returns:
            Empty dict on success, or {"error": ...} on failure.
        """
        thread_id = state.get("thread_id")
        project_id = state.get("project_id")
        response_text = state.get("response_text")

        if not thread_id or not project_id:
            logger.error("persist_node called without thread_id or project_id")
            return {"error": "Missing thread_id or project_id"}

        # 1. Save assistant message
        if response_text:
            try:
                await thread_repo.add_message(thread_id, role="assistant", content=response_text)
                logger.debug("Assistant message saved", extra={"thread_id": thread_id})
            except Exception as e:
                logger.exception("Failed to save assistant message", extra={"thread_id": thread_id})
                # Continue to save state anyway

        # 2. Save state_json (filter out large fields if desired)
        # We'll store the whole state minus messages and history to avoid bloat.
        state_to_save = dict(state)
        # Remove large fields that are not needed for reconstruction
        state_to_save.pop("messages", None)
        state_to_save.pop("history", None)
        state_to_save.pop("knowledge_chunks", None)
        # Could also limit size, but JSONB is fine.
        try:
            await thread_repo.save_state_json(thread_id, state_to_save)
            logger.debug("State JSON saved", extra={"thread_id": thread_id})
        except Exception as e:
            logger.exception("Failed to save state_json", extra={"thread_id": thread_id})

        # 3. Emit events
        if event_repo:
            # ai_response
            try:
                await event_repo.append(
                    stream_id=thread_id,
                    project_id=project_id,
                    event_type="ai_response",
                    payload={
                        "text": response_text,
                        "confidence": state.get("confidence"),
                        "requires_human": state.get("requires_human", False)
                    }
                )
            except Exception as e:
                logger.warning("Failed to emit ai_response event", extra={"thread_id": thread_id, "error": str(e)})

            # tool_called (if any)
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
                            "result": state.get("tool_result")
                        }
                    )
                except Exception as e:
                    logger.warning("Failed to emit tool_called event", extra={"thread_id": thread_id, "error": str(e)})

            # ticket_created (if escalation happened)
            if state.get("requires_human"):
                try:
                    await event_repo.append(
                        stream_id=thread_id,
                        project_id=project_id,
                        event_type="ticket_created",
                        payload={
                            "reason": "Human escalation requested",
                            "manager_notified": True  # assume we enqueued earlier
                        }
                    )
                except Exception as e:
                    logger.warning("Failed to emit ticket_created event", extra={"thread_id": thread_id, "error": str(e)})

        # 4. Trigger summarization (placeholder)
        # if summarizer and condition_met:
        #     asyncio.create_task(summarizer.summarize_and_save(thread_id))

        return {}  # no state changes

    return persist_node
