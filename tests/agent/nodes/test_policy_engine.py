from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from src.agent.nodes.policy_engine import create_policy_engine_node


@pytest.mark.asyncio
async def test_policy_engine_returns_typed_state_patch_and_emits_event():
    event_repo = AsyncMock()
    node = create_policy_engine_node(event_repo=event_repo)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.policy_engine.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "lifecycle": "cold",
                "intent": "ask_price",
                "dialog_state": {"last_intent": "ask_price", "repeat_count": 1},
                "confidence": 0.75,
            }
        )

    assert result["decision"] == "LLM_GENERATE"
    assert result["cta"] in {"book_consultation"}
    assert result["topic"] == "pricing"
    assert "dialog_state" in result
    event_repo.append.assert_awaited_once()


@pytest.mark.asyncio
async def test_policy_engine_loads_dialog_state_from_user_memory_when_missing_direct_state():
    node = create_policy_engine_node(event_repo=None)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.policy_engine.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "lifecycle": "interested",
                "intent": "ask_integration",
                "user_memory": {
                    "dialog_state": [
                        {
                            "key": "dialog_state",
                            "value": {
                                "last_intent": "ask_integration",
                                "repeat_count": 2,
                            },
                        }
                    ]
                },
            }
        )

    assert result["topic"] == "integration"
    assert result["dialog_state"]["repeat_count"] >= 3


@pytest.mark.asyncio
async def test_policy_engine_keeps_sales_cta_without_marking_handoff():
    node = create_policy_engine_node(event_repo=None)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.policy_engine.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "lifecycle": "warm",
                "intent": "sales",
                "dialog_state": {
                    "last_intent": "feedback",
                    "last_cta": "none",
                    "last_topic": "other",
                    "repeat_count": 0,
                    "lead_status": "warm",
                    "lifecycle": "warm",
                },
            }
        )

    assert result["decision"] == "LLM_GENERATE"
    assert result["cta"] == "call_manager"
    assert result["topic"] == "product"
    assert result["lead_status"] == "warm"
