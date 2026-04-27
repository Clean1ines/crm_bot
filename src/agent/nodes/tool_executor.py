"""
Tool executor node for LangGraph pipeline.

Executes a requested tool through the registry and returns a typed runtime
patch describing the outcome.
"""

import json

from src.agent.state import AgentState
from src.domain.runtime.tool_execution import ToolExecutionContext, ToolExecutionResult
from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)

MISSING_TOOL_TEXT = (
    "The requested action could not be executed because no tool was selected. "
    "The conversation has been handed off to a manager."
)
TOOL_FAILED_TEXT = "An error occurred while executing the requested action. The conversation has been handed off to a manager."


def create_tool_executor_node(tool_registry: ToolRegistry):
    """
    Create the tool executor node with an injected tool registry.
    """

    async def _tool_executor_node_impl(state: AgentState) -> dict[str, object]:
        context = ToolExecutionContext.from_state(state)
        if not context.tool_name:
            logger.warning("tool_executor_node called with no tool_name")
            return ToolExecutionResult(
                requires_human=True,
                response_text=MISSING_TOOL_TEXT,
            ).to_state_patch()

        logger.info(
            "Executing tool",
            extra={
                "tool_name": context.tool_name,
                "project_id": context.project_id,
                "thread_id": context.thread_id,
            },
        )

        try:
            result = await tool_registry.execute(
                context.tool_name,
                context.tool_args,
                context.execution_context(),
            )
            logger.debug(
                "Tool executed successfully", extra={"tool_name": context.tool_name}
            )
            return ToolExecutionResult(
                tool_result=result, requires_human=False
            ).to_state_patch()
        except Exception as exc:
            logger.exception(
                "Tool execution failed",
                extra={"tool_name": context.tool_name, "error": str(exc)},
            )
            return ToolExecutionResult(
                tool_result=None,
                requires_human=True,
                response_text=TOOL_FAILED_TEXT,
            ).to_state_patch()

    def _get_tool_executor_input_size(state: AgentState) -> int:
        context = ToolExecutionContext.from_state(state)
        return len(json.dumps(context.tool_args))

    def _get_tool_executor_output_size(result: dict[str, object]) -> int:
        return (
            len(json.dumps(result.get("tool_result", "")))
            if result.get("tool_result")
            else 0
        )

    async def tool_executor_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "tool_executor",
            _tool_executor_node_impl,
            state,
            get_input_size=_get_tool_executor_input_size,
            get_output_size=_get_tool_executor_output_size,
        )

    return tool_executor_node
