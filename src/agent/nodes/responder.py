"""
Responder node for the LangGraph pipeline.

Delivers the final response through the transport adapter and reports the
delivery outcome back into graph state.
"""

from typing import Any

from src.agent.state import AgentState
from src.domain.runtime.delivery import ResponseDeliveryContext, ResponseDeliveryResult
from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)

MISSING_CHAT_ID_TEXT = (
    "Failed to deliver the response because the chat identifier is missing. "
    "Please contact support."
)
SEND_FAILED_TEXT = (
    "The response could not be delivered right now. Please try again later or contact a manager."
)
SEND_EXCEPTION_TEXT = (
    "A technical error occurred while delivering the response. We are already looking into it."
)


def create_responder_node(tool_registry: ToolRegistry, thread_repo=None):
    """
    Create the delivery node with injected tool registry and optional thread repo.
    """

    async def _responder_node_impl(state: AgentState) -> dict[str, Any]:
        context = ResponseDeliveryContext.from_state(state)
        if not context.chat_id:
            logger.error("responder_node called with no chat_id")
            return ResponseDeliveryResult(
                message_sent=False,
                requires_human=True,
                response_text=MISSING_CHAT_ID_TEXT,
            ).to_state_patch()

        response_text = context.resolve_response_text()
        logger.debug(
            "Sending response",
            extra={
                "chat_id": context.chat_id,
                "project_id": context.project_id,
                "thread_id": context.thread_id,
                "response_preview": response_text[:50],
            },
        )

        try:
            result = await tool_registry.execute(
                "telegram.send_message",
                {"chat_id": context.chat_id, "text": response_text},
                context={"project_id": context.project_id, "thread_id": context.thread_id},
            )
            if result.get("ok"):
                logger.info("Message sent successfully", extra={"chat_id": context.chat_id})
                if context.thread_id and thread_repo:
                    try:
                        await thread_repo.add_message(
                            thread_id=context.thread_id,
                            role="assistant",
                            content=response_text,
                        )
                        logger.debug("Assistant message saved", extra={"thread_id": context.thread_id})
                    except Exception:
                        logger.exception(
                            "Failed to save assistant message",
                            extra={"thread_id": context.thread_id},
                        )

                return ResponseDeliveryResult(
                    message_sent=True,
                    response_text=None,
                ).to_state_patch()

            logger.error("Telegram send failed", extra={"chat_id": context.chat_id, "result": result})
            return ResponseDeliveryResult(
                message_sent=False,
                requires_human=True,
                response_text=SEND_FAILED_TEXT,
            ).to_state_patch()
        except Exception:
            logger.exception("Exception while sending message", extra={"chat_id": context.chat_id})
            return ResponseDeliveryResult(
                message_sent=False,
                requires_human=True,
                response_text=SEND_EXCEPTION_TEXT,
            ).to_state_patch()

    def _get_responder_input_size(state: AgentState) -> int:
        context = ResponseDeliveryContext.from_state(state)
        return len(context.resolve_response_text())

    def _get_responder_output_size(result: dict[str, Any]) -> int:
        return 1

    async def responder_node(state: AgentState) -> dict[str, Any]:
        return await log_node_execution(
            "responder",
            _responder_node_impl,
            state,
            get_input_size=_get_responder_input_size,
            get_output_size=_get_responder_output_size,
        )

    return responder_node
