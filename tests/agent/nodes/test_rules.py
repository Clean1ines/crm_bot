from unittest.mock import AsyncMock, patch

import pytest

from src.agent.nodes.rules import rules_node


@pytest.mark.asyncio
async def test_rules_node_requests_confirmation_for_angry_message():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node(
            {
                "user_input": "refund now",
                "dialog_state": {
                    "last_intent": None,
                    "last_cta": None,
                    "last_topic": None,
                    "repeat_count": 0,
                    "lead_status": "cold",
                    "lifecycle": "cold",
                    "handoff_confirmation_pending": False,
                },
            }
        )

    assert result["decision"] == "RESPOND"
    assert result["requires_human"] is False
    assert result["dialog_state"]["handoff_confirmation_pending"] is True


@pytest.mark.asyncio
async def test_rules_node_escalates_after_confirmation_reply():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node(
            {
                "user_input": "yes",
                "dialog_state": {
                    "last_intent": "handoff_request",
                    "last_cta": "call_manager",
                    "last_topic": "handoff",
                    "repeat_count": 1,
                    "lead_status": "warm",
                    "lifecycle": "warm",
                    "handoff_confirmation_pending": True,
                },
            }
        )

    assert result["decision"] == "ESCALATE"
    assert result["dialog_state"]["handoff_confirmation_pending"] is False


@pytest.mark.asyncio
async def test_rules_node_declines_handoff_and_requests_more_details():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node(
            {
                "user_input": "no, adding details",
                "dialog_state": {
                    "last_intent": "handoff_request",
                    "last_cta": "call_manager",
                    "last_topic": "handoff",
                    "repeat_count": 1,
                    "lead_status": "warm",
                    "lifecycle": "warm",
                    "handoff_confirmation_pending": True,
                },
            }
        )

    assert result["decision"] == "RESPOND"
    assert result["requires_human"] is False
    assert result["dialog_state"]["handoff_confirmation_pending"] is False
