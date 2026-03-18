"""
Responder node for LangGraph pipeline.

Sends the final response to the user via Telegram.
Prioritizes tool_result over response_text, falls back to a default message.
"""

from typing import Dict, Any

from src.core.logging import get_logger
from src.agent.state import AgentState
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)


def create_responder_node(tool_registry: ToolRegistry):
    """
    Factory function that creates a responder node with injected ToolRegistry.

    Args:
        tool_registry: ToolRegistry instance for sending messages.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        (usually empty on success, or with requires_human=True on failure).
    """
    async def responder_node(state: AgentState) -> Dict[str, Any]:
        """
        Send the final response to the user.

        Expected state fields:
          - chat_id: int (Telegram chat ID)
          - tool_result: optional, if present and has a 'text' field, use it.
          - response_text: optional fallback text.
          - project_id: str (for logging)
          - thread_id: str (for logging)

        Returns a dict with updates to the state:
          - empty dict on success
          - if sending fails: {"requires_human": True, "response_text": fallback}
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

        # Log what we're sending
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
                    "text": response_text,
                    "parse_mode": "Markdown"  # optional, could be configurable
                },
                context={
                    "project_id": state.get("project_id"),
                    "thread_id": state.get("thread_id")
                }
            )
            if result.get("ok"):
                logger.info("Message sent successfully", extra={"chat_id": chat_id})
                return {}  # no state changes needed
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

    return responder_node
