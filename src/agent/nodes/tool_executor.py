"""
Tool executor node for LangGraph pipeline.

Executes a requested tool through the registry and returns a typed runtime
patch describing the outcome.
"""

import json
from typing import cast

from src.agent.state import AgentState
from src.domain.runtime.response_generation import GenerationMode
from src.domain.runtime.state_contracts import RuntimeStateInput
from src.domain.runtime.tool_execution import (
    ToolSafeErrorCode,
    ToolExecutionContext,
    ToolExecutionOutcome,
    ToolExecutionResult,
    ToolExecutionStatus,
    exception_safe_error_code,
)
from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)

MISSING_TOOL_TEXT = (
    "The requested action could not be executed because no tool was selected. "
    "Please try again later."
)


def create_tool_executor_node(tool_registry: ToolRegistry):
    """
    Create the tool executor node with an injected tool registry.
    """

    async def _tool_executor_node_impl(state: AgentState) -> dict[str, object]:
        context = ToolExecutionContext.from_state(cast(RuntimeStateInput, state))
        if not context.tool_name:
            logger.warning("tool_executor_node called with no tool_name")
            patch = ToolExecutionResult(
                requires_human=False,
                response_text=MISSING_TOOL_TEXT,
                status=ToolExecutionStatus.FAILED,
                safe_error_code=ToolSafeErrorCode.MISSING_TOOL_SELECTION.value,
            ).to_state_patch()
            patch["generation_mode"] = GenerationMode.TOOL_RESULT_RESPONSE.value
            return dict(patch)

        logger.info(
            "Executing tool",
            extra={
                "tool_name": context.tool_name,
                "project_id": context.project_id,
                "thread_id": context.thread_id,
            },
        )

        try:
            result: object = await tool_registry.execute(
                context.tool_name,
                dict(context.tool_args),
                dict(context.execution_context()),
            )
            if isinstance(result, ToolExecutionOutcome):
                outcome = result
            else:
                logger.error(
                    "Tool registry returned invalid outcome contract",
                    extra={
                        "tool_name": context.tool_name,
                        "result_type": type(result).__name__,
                    },
                )
                outcome = ToolExecutionOutcome.failed(
                    safe_error_code=ToolSafeErrorCode.INVALID_TOOL_OUTCOME
                )
            logger.debug(
                "Tool executed",
                extra={
                    "tool_name": context.tool_name,
                    "tool_execution_status": outcome.status.value,
                },
            )
        except Exception as exc:
            logger.exception(
                "Tool execution failed",
                extra={
                    "tool_name": context.tool_name,
                    "error_type": type(exc).__name__,
                },
            )
            outcome = ToolExecutionOutcome(
                status=ToolExecutionStatus.FAILED,
                payload=None,
                safe_error_code=exception_safe_error_code(exc).value,
            )

        patch = ToolExecutionResult(
            tool_result=outcome.payload,
            requires_human=outcome.status is ToolExecutionStatus.REQUIRES_HUMAN,
            response_text=(
                outcome.response_text
                if outcome.status is ToolExecutionStatus.REQUIRES_HUMAN
                else None
            ),
            status=outcome.status,
            safe_error_code=outcome.safe_error_code,
            tool_response_text=(
                outcome.response_text
                if outcome.status is ToolExecutionStatus.SUCCEEDED
                else None
            ),
        ).to_state_patch()
        if outcome.status in {
            ToolExecutionStatus.SUCCEEDED,
            ToolExecutionStatus.FAILED,
        }:
            patch["generation_mode"] = GenerationMode.TOOL_RESULT_RESPONSE.value
        return dict(patch)

    def _get_tool_executor_input_size(state: AgentState) -> int:
        context = ToolExecutionContext.from_state(cast(RuntimeStateInput, state))
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
