from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.nodes.intent_extractor import create_intent_extractor_node


@pytest.mark.asyncio
async def test_intent_extractor_returns_empty_when_no_input():
    llm = AsyncMock()
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.intent_extractor.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({})

    assert result == {}
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_intent_extractor_parses_json_block_into_state_patch():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content='''```json\n{"intent":"support","cta":"none","features":{"crm":0.8},"topic":"support","cta_hint":null,"emotion":"negative","is_repeat_like":true}\n```'''
        )
    )
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.intent_extractor.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({"user_input": "help"})

    assert result["intent"] == "support"
    assert result["features"] == {"crm": 0.8}
    assert result["is_repeat_like"] is True
