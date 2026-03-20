"""
Persist node for LangGraph pipeline.

Saves assistant message and state to the database, and emits events
for auditing and analytics. Also extracts and stores user memory
based on simple keyword rules.
"""

from typing import Dict, Any, Optional

from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.event_repository import EventRepository
from src.database.repositories.memory_repository import MemoryRepository

logger = get_logger(__name__)


def create_persist_node(
    thread_repo: ThreadRepository,
    event_repo: Optional[EventRepository] = None,
    memory_repo: Optional[MemoryRepository] = None,
    summarizer: Optional[Any] = None  # placeholder for summarizer service
):
    """
    Factory function that creates a persist node with injected dependencies.

    Args:
        thread_repo: ThreadRepository instance for saving messages and state.
        event_repo: Optional EventRepository for emitting events.
        memory_repo: Optional MemoryRepository for storing user memory.
        summarizer: Optional SummarizerService for background summarization.

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
          - response_text: str (final answer)
          - tool_name: optional, if tool was called
          - tool_args: optional
          - requires_human: bool, if escalation happened
          - client_id: optional, for memory storage

        Actions:
          1. Save assistant message to messages table.
          2. Save state_json to threads table.
          3. Emit events:
             - ai_response (always)
             - tool_called (if tool was used)
             - ticket_created (if escalation happened)
          4. Extract user memory from user_input and store (if memory_repo).
          5. Trigger background summarization if needed (placeholder).

        Returns:
            Empty dict on success, or {"error": ...} on failure.
        """
        thread_id = state.get("thread_id")
        project_id = state.get("project_id")
        response_text = state.get("response_text")
        user_input = state.get("user_input", "").lower()
        client_id = state.get("client_id")

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
        state_to_save = dict(state)
        state_to_save.pop("messages", None)
        state_to_save.pop("history", None)
        state_to_save.pop("knowledge_chunks", None)
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
                            "manager_notified": True
                        }
                    )
                except Exception as e:
                    logger.warning("Failed to emit ticket_created event", extra={"thread_id": thread_id, "error": str(e)})

        # 4. Store user memory (simple keyword rules)
        if memory_repo and client_id and user_input:
            try:
                # Lifecycle detection
                lifecycle_keywords = {
                    "хочу": "warm", "давайте": "warm", "подключить": "warm", "начнем": "warm",
                    "как оплатить": "hot", "куда платить": "hot"
                }
                for kw, stage in lifecycle_keywords.items():
                    if kw in user_input:
                        await memory_repo.set(
                            project_id=project_id,
                            client_id=client_id,
                            key="lifecycle",
                            value={"stage": stage},
                            type_="lifecycle"
                        )
                        logger.debug("Stored lifecycle memory", extra={"stage": stage, "client_id": client_id})
                        break

                # Rejection (no calls)
                if "не хочу звонок" in user_input:
                    await memory_repo.set(
                        project_id=project_id,
                        client_id=client_id,
                        key="calls",
                        value=False,
                        type_="rejection"
                    )
                    logger.debug("Stored rejection memory: no calls")

                # Behavior (price sensitivity)
                if any(phrase in user_input for phrase in ["дорого", "слишком дорого"]):
                    await memory_repo.set(
                        project_id=project_id,
                        client_id=client_id,
                        key="price_sensitivity",
                        value="high",
                        type_="behavior"
                    )
                    logger.debug("Stored price sensitivity memory")

                # Business context extraction (simple)
                business_phrases = ["у меня салон", "мой бизнес", "я из"]
                for phrase in business_phrases:
                    if phrase in user_input:
                        # Try to extract business type after the phrase
                        # For simplicity, set a default or keep as is
                        await memory_repo.set(
                            project_id=project_id,
                            client_id=client_id,
                            key="business_type",
                            value="salon",  # placeholder, could be smarter
                            type_="context"
                        )
                        logger.debug("Stored business context")
                        break

                # Issues
                issue_keywords = ["не работает", "бесит", "ошибка", "жалоба"]
                if any(kw in user_input for kw in issue_keywords):
                    await memory_repo.set(
                        project_id=project_id,
                        client_id=client_id,
                        key="last_issue",
                        value=user_input[:200],
                        type_="issues"
                    )
                    logger.debug("Stored issue memory")

            except Exception as e:
                logger.exception("Failed to store user memory", extra={"client_id": client_id})

        # 5. Trigger summarization (placeholder)
        # if summarizer and condition_met:
        #     asyncio.create_task(summarizer.summarize_and_save(thread_id))

        return {}  # no state changes

    def _get_persist_input_size(state: AgentState) -> int:
        return 0  # no meaningful input size

    def _get_persist_output_size(result: Dict[str, Any]) -> int:
        return 0  # output is empty dict

    async def persist_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "persist",
            _persist_node_impl,
            state,
            get_input_size=_get_persist_input_size,
            get_output_size=_get_persist_output_size
        )

    return persist_node
