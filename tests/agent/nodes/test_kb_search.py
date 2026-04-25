from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.kb_search import create_kb_search_node


@pytest.mark.asyncio
async def test_kb_search_returns_empty_chunks_when_context_missing():
    node = create_kb_search_node(tool_registry=MagicMock())

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.kb_search.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({})

    assert result == {"knowledge_chunks": []}


@pytest.mark.asyncio
async def test_kb_search_normalizes_tool_results():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value={
            "results": [
                {"id": "chunk-1", "score": 0.9, "content": "abc"},
                {"score": None, "content": "xyz"},
            ]
        }
    )
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.kb_search.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({"project_id": "project-1", "user_input": "hello"})

    assert result == {
        "knowledge_chunks": [
            {"id": "chunk-1", "score": 0.9, "content": "abc"},
            {"id": "no-id-1", "score": None, "content": "xyz"},
        ]
    }
    tool_registry.execute.assert_awaited_once()
