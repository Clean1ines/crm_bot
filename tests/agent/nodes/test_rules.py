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


@pytest.mark.asyncio
async def test_rules_node_allows_human_in_the_loop_information_question():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node(
            {"user_input": "Поддерживается ли human-in-the-loop?"}
        )

    assert result["decision"] == "PROCEED_TO_LLM"


@pytest.mark.asyncio
async def test_rules_node_allows_negative_handoff_request():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node({"user_input": "Не зови менеджера"})

    assert result["decision"] == "PROCEED_TO_LLM"


@pytest.mark.asyncio
async def test_rules_node_allows_negative_handoff_request_with_positive_substring():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node({"user_input": "Не хочу поговорить с менеджером"})

    assert result["decision"] == "PROCEED_TO_LLM"


@pytest.mark.asyncio
async def test_rules_node_escalates_explicit_handoff_request():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node({"user_input": "Позови менеджера"})

    assert result["decision"] == "ESCALATE"
