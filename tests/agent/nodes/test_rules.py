from unittest.mock import AsyncMock, patch

import pytest

from src.agent.nodes.load_state import create_load_state_node
from src.agent.nodes.rules import rules_node
from src.domain.runtime.persistence import PersistenceContext


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
                "user_input": "ВЫ МЕНЯ БЕСИТЕ, СЕРВИС НЕ РАБОТАЕТ",
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
@pytest.mark.parametrize(
    "user_input", ["PDF", "PDF?", "А PDF?", "API", "А API?", "CRM", "SQL"]
)
async def test_rules_node_allows_short_caps_technical_acronyms(user_input):
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node({"user_input": user_input})

    assert result["decision"] == "PROCEED_TO_LLM"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input",
    [
        "refund",
        "chargeback",
        "жалоба",
        "удалить аккаунт",
        "это дорого",
    ],
)
async def test_rules_node_does_not_treat_business_risk_as_anger(user_input):
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await rules_node({"user_input": user_input})

    assert result["decision"] == "PROCEED_TO_LLM"


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
    assert result["turn_relation"] == "short_reply"


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
    assert result["turn_relation"] == "short_reply"


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


@pytest.mark.asyncio
async def test_handoff_decline_path_preserves_query_without_stale_memory_candidates():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    thread_read_repo = AsyncMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
        }
    )
    runtime_repo = AsyncMock()
    runtime_repo.get_analytics_view = AsyncMock(return_value=None)
    runtime_repo.get_state_json = AsyncMock(
        return_value={
            "intent": "pricing",
            "topic": "pricing",
            "emotion": "negative",
            "turn_relation": "new_topic",
            "conversation_context": {"last_standalone_query": "Какие у вас тарифы?"},
            "dialog_state": {"handoff_confirmation_pending": True},
        }
    )
    message_repo = AsyncMock()
    message_repo.get_messages_for_langgraph = AsyncMock(return_value=[])
    load_state = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=message_repo,
        thread_runtime_state_repo=runtime_repo,
        project_repo=AsyncMock(),
    )

    loaded = await load_state({"thread_id": "thread-1", "user_input": "Нет"})
    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        rule_patch = await rules_node({**loaded, "user_input": "Нет"})

    context = PersistenceContext.from_state(
        {**loaded, **rule_patch, "user_input": "Нет"}
    )

    assert context.state_payload is not None
    assert context.state_payload["conversation_context"]["last_standalone_query"] == (
        "Какие у вас тарифы?"
    )
    candidate_keys = {candidate.key for candidate in context.memory_write_candidates()}
    assert "price_sensitivity" not in candidate_keys
    assert "pricing_objection" not in candidate_keys
    assert "active_issue" not in candidate_keys


@pytest.mark.asyncio
async def test_anger_rule_uses_current_input_after_stale_short_reply_is_scrubbed():
    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    thread_read_repo = AsyncMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
        }
    )
    runtime_repo = AsyncMock()
    runtime_repo.get_analytics_view = AsyncMock(return_value=None)
    runtime_repo.get_state_json = AsyncMock(
        return_value={
            "turn_relation": "short_reply",
            "conversation_context": {"last_standalone_query": "Какие у вас тарифы?"},
            "dialog_state": {"handoff_confirmation_pending": False},
        }
    )
    message_repo = AsyncMock()
    message_repo.get_messages_for_langgraph = AsyncMock(return_value=[])
    load_state = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=message_repo,
        thread_runtime_state_repo=runtime_repo,
        project_repo=AsyncMock(),
    )
    user_input = "Это бесит, ничего не работает"

    loaded = await load_state({"thread_id": "thread-1", "user_input": user_input})
    with patch(
        "src.agent.nodes.rules.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        rule_patch = await rules_node({**loaded, "user_input": user_input})

    context = PersistenceContext.from_state(
        {**loaded, **rule_patch, "user_input": user_input}
    )

    assert context.state_payload is not None
    assert (
        context.state_payload["conversation_context"]["last_standalone_query"]
        == user_input.lower()
    )
