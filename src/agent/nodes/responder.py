"""
Responder node for LangGraph pipeline.

Sends the final response to the user via Telegram.
Saves the assistant message to the database for context in future interactions.
"""

from typing import Dict, Any, Optional

from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)


def create_responder_node(tool_registry: ToolRegistry, thread_repo=None):
    """
    Factory function that creates a responder node with injected ToolRegistry and ThreadRepository.

    Args:
        tool_registry: ToolRegistry instance for sending messages.
        thread_repo: Optional ThreadRepository for saving assistant messages to history.

    Returns:
        An async function that takes an AgentState dict and returns updates.
    """
    async def _responder_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Send the final response to the user and save it to history.

        Expected state fields:
          - chat_id: int (Telegram chat ID)
          - tool_result: optional, if present and has a 'text' field, use it.
          - response_text: optional fallback text.
          - project_id: str (for logging)
          - thread_id: str (for saving message)

        Returns a dict with updates to the state:
          - on success: {"message_sent": True, "response_text": None}
          - if sending fails: {"requires_human": True, "response_text": fallback message}
        """
        chat_id = state.get("chat_id")
        if not chat_id:
            logger.error("responder_node called with no chat_id")
            return {
                "requires_human": True,
                "response_text": "Ошибка отправки ответа: отсутствует идентификатор чата. Пожалуйста, обратитесь к поддержке."
            }

        # Determine final response text
        response_text = None
        tool_result = state.get("tool_result")
        if tool_result and isinstance(tool_result, dict) and tool_result.get("text"):
            response_text = tool_result["text"]
        elif state.get("response_text"):
            response_text = state["response_text"]
        else:
            response_text = "Извините, не удалось сформировать ответ."

        logger.debug("Sending response",
                     extra={"chat_id": chat_id,
                            "project_id": state.get("project_id"),
                            "thread_id": state.get("thread_id"),
                            "response_preview": response_text[:50]})

        # Call telegram.send_message tool
        try:
            result = await tool_registry.execute(
                "telegram.send_message",
                {
                    "chat_id": chat_id,
                    "text": response_text
                },
                context={
                    "project_id": state.get("project_id"),
                    "thread_id": state.get("thread_id")
                }
            )
            if result.get("ok"):
                logger.info("Message sent successfully", extra={"chat_id": chat_id})

                # Save assistant message to database if repo available
                thread_id = state.get("thread_id")
                if thread_id and thread_repo:
                    try:
                        await thread_repo.add_message(
                            thread_id=thread_id,
                            role="assistant",
                            content=response_text,
                        )
                        logger.debug("Assistant message saved", extra={"thread_id": thread_id})
                    except Exception as e:
                        logger.exception("Failed to save assistant message", extra={"thread_id": thread_id})

                # Message sent, clear response_text to avoid double-send
                return {"message_sent": True, "response_text": None}
            else:
                logger.error("Telegram send failed", extra={"chat_id": chat_id, "result": result})
                return {
                    "requires_human": True,
                    "response_text": "Не удалось отправить ответ. Пожалуйста, попробуйте позже или обратитесь к менеджеру."
                }
        except Exception as e:
            logger.exception("Exception while sending message", extra={"chat_id": chat_id})
            return {
                "requires_human": True,
                "response_text": "Произошла техническая ошибка при отправке ответа. Мы уже работаем над её устранением."
            }

    def _get_responder_input_size(state: AgentState) -> int:
        return len(state.get("response_text", "")) + (len(str(state.get("tool_result", {}))) if state.get("tool_result") else 0)

    def _get_responder_output_size(result: Dict[str, Any]) -> int:
        return 1  # success/failure flag

    async def responder_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "responder",
            _responder_node_impl,
            state,
            get_input_size=_get_responder_input_size,
            get_output_size=_get_responder_output_size
        )

    return responder_node
