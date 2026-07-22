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


@pytest.mark.asyncio
async def test_policy_engine_requests_handoff_confirmation_before_escalation():
    node = create_policy_engine_node(event_repo=None)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.policy_engine.logger") as logger,
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "lifecycle": "warm",
                "intent": "handoff_request",
                "user_input": "Хочу поговорить с менеджером по интеграции CRM",
                "dialog_state": {
                    "last_intent": "sales",
                    "last_cta": "call_manager",
                    "last_topic": "product",
                    "repeat_count": 1,
                    "lead_status": "warm",
                    "lifecycle": "warm",
                    "handoff_confirmation_pending": False,
                },
            }
        )

    assert result["decision"] == "RESPOND"
    assert "requires_human" not in result
    assert result["dialog_state"]["handoff_confirmation_pending"] is True
    assert "менеджер" in str(result["response_text"]).lower()
    trace = [
        call
        for call in logger.info.call_args_list
        if call.args and call.args[0] == "Policy routing trace"
    ][-1]
    assert trace.kwargs["extra"]["handoff_signal_source"] == "rules_explicit_request"


@pytest.mark.asyncio
async def test_policy_engine_ordinary_merge_keeps_policy_route_over_intent_flags():
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
                "lifecycle": "cold",
                "intent": "handoff_request",
                "user_input": "Позовите менеджера",
                "turn_relation": "new_topic",
                "knowledge_query": "stale resolved query",
                "should_search_kb": True,
                "should_generate_answer": True,
                "should_offer_manager": True,
                "dialog_state": {
                    "last_intent": "sales",
                    "last_cta": None,
                    "last_topic": "product",
                    "repeat_count": 1,
                    "lead_status": "cold",
                    "lifecycle": "cold",
                    "handoff_confirmation_pending": False,
                },
            }
        )

    assert result["decision"] == "RESPOND"
    assert result["should_search_kb"] is False
    assert result["should_generate_answer"] is False
    assert result["knowledge_query"] is None
    assert result["turn_relation"] == "new_topic"
    assert result["should_offer_manager"] is False


@pytest.mark.asyncio
async def test_policy_engine_routes_informational_manager_mention_to_generation():
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
                "lifecycle": "active_client",
                "intent": "support",
                "topic": "support",
                "cta": "none",
                "user_input": "Как менеджер работает с обращениями?",
                "features": {"handoff": 0.95},
                "dialog_state": {
                    "last_intent": "sales",
                    "last_cta": None,
                    "last_topic": "product",
                    "repeat_count": 1,
                    "lead_status": "active_client",
                    "lifecycle": "active_client",
                    "handoff_confirmation_pending": False,
                },
            }
        )

    assert result["decision"] == "LLM_GENERATE"
    assert result["topic"] == "support"
    assert result["cta"] == "none"
    assert "response_text" not in result


@pytest.mark.asyncio
async def test_policy_engine_marks_llm_handoff_classification_without_claiming_explicit_rule():
    node = create_policy_engine_node(event_repo=None)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.policy_engine.logger") as logger,
    ):
        await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "lifecycle": "warm",
                "intent": "handoff_request",
                "topic": "handoff",
                "user_input": "Что означает human handoff?",
                "dialog_state": {
                    "last_topic": "support",
                    "repeat_count": 1,
                    "handoff_confirmation_pending": False,
                },
            }
        )

    trace = [
        call
        for call in logger.info.call_args_list
        if call.args and call.args[0] == "Policy routing trace"
    ][-1]
    assert trace.kwargs["extra"]["handoff_signal_source"] == "intent_classified_handoff"


@pytest.mark.asyncio
async def test_policy_engine_prefers_valid_current_turn_topic():
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
                "lifecycle": "active_client",
                "intent": "other",
                "topic": "product",
                "features": {},
                "dialog_state": {"last_topic": "pricing", "repeat_count": 1},
            }
        )

    assert result["decision"] == "LLM_GENERATE"
    assert result["topic"] == "product"


@pytest.mark.asyncio
async def test_policy_engine_falls_back_when_current_turn_topic_is_invalid():
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
                "lifecycle": "active_client",
                "intent": "other",
                "topic": "nonsense",
                "features": {},
                "dialog_state": {"last_topic": "pricing", "repeat_count": 1},
            }
        )

    assert result["decision"] == "LLM_GENERATE"
    assert result["topic"] == "other"


@pytest.mark.asyncio
async def test_policy_engine_keeps_complaint_risk_handoff_path():
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
                "intent": "support",
                "topic": "support",
                "features": {"complaint": 0.95},
                "dialog_state": {
                    "last_topic": "support",
                    "repeat_count": 1,
                    "handoff_confirmation_pending": False,
                },
            }
        )

    assert result["decision"] == "RESPOND"
    assert result["dialog_state"]["handoff_confirmation_pending"] is True
    assert "менеджер" in str(result["response_text"]).lower()
