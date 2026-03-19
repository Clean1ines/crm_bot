"""
Tool executor node for LangGraph pipeline

Executes a tool using the ToolRegistry and stores the result in the state.
Handles errors by setting requires_human=True and providing fallback response.
"""

import json
from typing import Dict, Any, Optional

from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)


def create_tool_executor_node(tool_registry: ToolRegistry):
    """
    Factory function that creates a tool_executor node with injected ToolRegistry.

    Args:
        tool_registry: ToolRegistry instance for executing tools.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with the result of tool execution (tool_result) and possibly updated
        requires_human flag.
    """
    async def _tool_executor_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Execute the tool specified in the state.

        Expected state fields:
          - tool_name: str
          - tool_args: dict
          - project_id: str (for context)
          - thread_id: str (for context)

        Returns a dict with updates to the state:
          - tool_result: any (result from tool execution)
          - requires_human: bool (set to True if tool failed or not found)
          - response_text: optional fallback message if tool failed
        """
        tool_name = state.get("tool_name")
        tool_args = state.get("tool_args", {})
        project_id = state.get("project_id")
        thread_id = state.get("thread_id")

        if not tool_name:
            logger.warning("tool_executor_node called with no tool_name")
            return {
                "requires_human": True,
                "response_text": "Не удалось выполнить действие (инструмент не указан). Передано менеджеру."
            }

        # Prepare context for tool execution (minimal)
        context = {
            "project_id": project_id,
            "thread_id": thread_id,
        }

        logger.info("Executing tool", extra={
            "tool_name": tool_name,
            "project_id": project_id,
            "thread_id": thread_id
        })

        try:
            result = await tool_registry.execute(tool_name, tool_args, context)
            logger.debug("Tool executed successfully", extra={"tool_name": tool_name})
            return {
                "tool_result": result,
                "requires_human": False  # assume success, but could be overridden by tool logic
            }
        except Exception as e:
            logger.exception("Tool execution failed", extra={"tool_name": tool_name, "error": str(e)})
            return {
                "requires_human": True,
                "response_text": f"Произошла ошибка при выполнении запроса. Передано менеджеру.",
                "tool_result": None
            }

    def _get_tool_executor_input_size(state: AgentState) -> int:
        # approximate input size by JSON string length of tool_args
        args = state.get("tool_args", {})
        return len(json.dumps(args))

    def _get_tool_executor_output_size(result: Dict[str, Any]) -> int:
        # approximate output size
        return len(json.dumps(result.get("tool_result", ""))) if result.get("tool_result") else 0

    async def tool_executor_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "tool_executor",
            _tool_executor_node_impl,
            state,
            get_input_size=_get_tool_executor_input_size,
            get_output_size=_get_tool_executor_output_size
        )

    return tool_executor_node
