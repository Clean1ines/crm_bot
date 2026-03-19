"""
Escalation node for LangGraph pipeline.

Marks a thread as requiring human intervention, creates a task in the queue,
and updates the state to indicate human escalation.
"""

from typing import Dict, Any

from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.database.models import ThreadStatus
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.queue_repository import QueueRepository

logger = get_logger(__name__)


def create_escalate_node(
    thread_repo: ThreadRepository,
    queue_repo: QueueRepository
):
    """
    Factory function that creates an escalate node with injected repository dependencies.

    Args:
        thread_repo: ThreadRepository instance for updating thread status.
        queue_repo: QueueRepository instance for enqueueing manager notification.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with updates to the state (requires_human=True, response_text).
    """
    async def _escalate_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Escalate the conversation to a human manager.

        Expected state fields:
          - thread_id: str
          - project_id: str (optional, used for logging)
          - user_input: str (optional, used for notification)

        Actions:
          1. Update thread status to MANUAL.
          2. Enqueue a 'notify_manager' task with relevant payload.
          3. Set requires_human=True and a standard response text in the state.

        Returns a dict with updates to the state.
        """
        thread_id = state.get("thread_id")
        project_id = state.get("project_id")
        user_input = state.get("user_input", "")

        if not thread_id:
            logger.error("escalate_node called with no thread_id")
            return {
                "requires_human": True,
                "response_text": "Ошибка эскалации: отсутствует идентификатор диалога. Пожалуйста, обратитесь к поддержке."
            }

        logger.info("Escalating thread", extra={"thread_id": thread_id, "project_id": project_id, "user_input": user_input[:50]})

        # 1. Update thread status to MANUAL
        try:
            await thread_repo.update_status(thread_id, ThreadStatus.MANUAL)
            logger.debug("Thread status updated to MANUAL", extra={"thread_id": thread_id})
        except Exception as e:
            logger.exception("Failed to update thread status", extra={"thread_id": thread_id})
            # Continue anyway, but log error

        # 2. Enqueue manager notification task
        try:
            await queue_repo.enqueue(
                task_type="notify_manager",
                payload={
                    "thread_id": thread_id,
                    "project_id": project_id,
                    "message": user_input[:200]  # rename user_input to message for worker
                }
            )
            logger.debug("Manager notification enqueued", extra={"thread_id": thread_id})
        except Exception as e:
            logger.exception("Failed to enqueue manager notification", extra={"thread_id": thread_id})

        # 3. Return updates to state
        return {
            "requires_human": True,
            "response_text": "Ваш вопрос передан менеджеру. Ожидайте ответа в ближайшее время.",
            "tool_result": None  # ensure no leftover tool result
        }

    def _get_escalate_input_size(state: AgentState) -> int:
        return len(state.get("user_input", ""))

    def _get_escalate_output_size(result: Dict[str, Any]) -> int:
        return len(result.get("response_text", ""))

    async def escalate_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "escalate",
            _escalate_node_impl,
            state,
            get_input_size=_get_escalate_input_size,
            get_output_size=_get_escalate_output_size
        )

    return escalate_node
