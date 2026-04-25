from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.tool_executor import create_tool_executor_node


@pytest.mark.asyncio
async def test_tool_executor_returns_human_fallback_when_tool_missing():
    node = create_tool_executor_node(tool_registry=MagicMock())

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.tool_executor.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({"project_id": "project-1"})

    assert result["requires_human"] is True
    assert result["tool_result"] is None


@pytest.mark.asyncio
async def test_tool_executor_returns_tool_result_on_success():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(return_value={"ok": True, "value": 1})
    node = create_tool_executor_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.tool_executor.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node(
            {
                "tool_name": "crm.create",
                "tool_args": {"name": "Alice"},
                "project_id": "project-1",
                "thread_id": "thread-1",
            }
        )

    assert result == {"tool_result": {"ok": True, "value": 1}, "requires_human": False}
    tool_registry.execute.assert_awaited_once()
