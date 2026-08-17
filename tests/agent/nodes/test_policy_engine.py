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
    assert result["cta"] == "none"
    assert result["dialog_state"]["last_cta"] is None
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
                "topic": "integration",
                "turn_relation": "continuation",
                "is_repeat_like": True,
                "user_memory": {
                    "dialog_state": [
                        {
                            "key": "dialog_state",
                            "value": {
                                "last_intent": "ask_integration",
                                "last_topic": "integration",
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
async def test_policy_engine_keeps_sales_advisory_cta_out_of_pending_state():
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
    assert result["cta"] == "none"
    assert result["dialog_state"]["last_cta"] is None
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
async def test_policy_engine_preserves_contextual_knowledge_query_for_continuation():
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
                "cta": "none",
                "user_input": "а как его подключить?",
                "turn_relation": "continuation",
                "knowledge_query": "Как подключить менеджерский контур?",
                "knowledge_query_source": "model_contextual",
                "should_search_kb": True,
                "should_generate_answer": True,
                "should_offer_manager": False,
                "dialog_state": {
                    "last_intent": "other",
                    "last_cta": None,
                    "last_topic": "product",
                    "repeat_count": 0,
                    "lead_status": "active_client",
                    "lifecycle": "active_client",
                },
            }
        )

    assert result["decision"] == "LLM_GENERATE"
    assert result["knowledge_query"] == "Как подключить менеджерский контур?"
    assert result["knowledge_query_source"] == "model_contextual"
    assert result["should_search_kb"] is True


@pytest.mark.asyncio
async def test_policy_engine_suppresses_only_normalized_false_manager_offer():
    node = create_policy_engine_node(event_repo=None)

    false_offer = await node(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "lifecycle": "active_client",
            "intent": "support",
            "topic": "support",
            "cta": "none",
            "user_input": "Как подключить менеджерский контур?",
            "turn_relation": "new_topic",
            "should_search_kb": True,
            "should_generate_answer": True,
            "should_offer_manager": True,
            "normalization_flags": {"action_cta_downgraded": True},
            "dialog_state": {"repeat_count": 0},
        }
    )

    legitimate_offer = await node(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "lifecycle": "active_client",
            "intent": "support",
            "topic": "support",
            "cta": "call_manager",
            "user_input": "Можно ли получить персональный расчёт?",
            "turn_relation": "new_topic",
            "should_search_kb": True,
            "should_generate_answer": True,
            "should_offer_manager": True,
            "dialog_state": {"repeat_count": 0},
        }
    )

    assert false_offer["decision"] == "LLM_GENERATE"
    assert false_offer["should_offer_manager"] is False
    assert legitimate_offer["decision"] == "LLM_GENERATE"
    assert legitimate_offer["should_offer_manager"] is True


@pytest.mark.asyncio
async def test_policy_engine_clears_query_when_search_is_forbidden_by_template_route():
    node = create_policy_engine_node(event_repo=None)

    result = await node(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "domain": "greeting",
            "intent": "other",
            "topic": "other",
            "cta": "none",
            "turn_relation": "continuation",
            "knowledge_query": "Как подключить менеджерский контур?",
            "knowledge_query_source": "model_contextual",
            "should_search_kb": True,
            "should_generate_answer": True,
            "dialog_state": {"repeat_count": 0},
        }
    )

    assert result["decision"] == "RESPOND_TEMPLATE"
    assert result["should_search_kb"] is False
    assert result.get("knowledge_query") is None


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
async def test_policy_engine_does_not_escalate_long_new_topic_business_sequence():
    node = create_policy_engine_node(event_repo=None)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    questions = [
        ("Что такое Axole?", "product"),
        ("Опиши Axole одним предложением.", "product"),
        ("Зачем использовать Axole вместо обычного AI-бота?", "product"),
        ("Чем отличается клиентский бот от менеджерского?", "product"),
        ("Можно ли встроить чат-виджет?", "integration"),
        ("Как выглядит запуск?", "product"),
        ("Каким компаниям подходит Axole?", "product"),
    ]
    dialog_state = {
        "last_intent": None,
        "last_topic": None,
        "repeat_count": 0,
        "lead_status": "warm",
        "lifecycle": "warm",
    }

    with patch(
        "src.agent.nodes.policy_engine.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        repeat_counts = []
        for user_input, topic in questions:
            result = await node(
                {
                    "thread_id": "thread-1",
                    "project_id": "project-1",
                    "lifecycle": "warm",
                    "intent": "other",
                    "topic": topic,
                    "cta": "call_manager",
                    "user_input": user_input,
                    "turn_relation": "new_topic",
                    "is_repeat_like": False,
                    "should_search_kb": True,
                    "should_generate_answer": True,
                    "should_offer_manager": True,
                    "dialog_state": dialog_state,
                }
            )
            assert result["decision"] == "LLM_GENERATE"
            assert result["should_search_kb"] is True
            assert result["should_generate_answer"] is True
            assert "response_text" not in result
            dialog_state = result["dialog_state"]
            repeat_counts.append(dialog_state["repeat_count"])

    assert repeat_counts == [0, 0, 0, 0, 0, 0, 0]


@pytest.mark.asyncio
async def test_policy_engine_escalates_only_real_repeat_streak():
    node = create_policy_engine_node(event_repo=None)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    dialog_state = {
        "last_intent": "pricing",
        "last_topic": "pricing",
        "repeat_count": 2,
        "lead_status": "warm",
        "lifecycle": "warm",
        "handoff_confirmation_pending": False,
    }

    with patch(
        "src.agent.nodes.policy_engine.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "lifecycle": "warm",
                "intent": "pricing",
                "topic": "pricing",
                "user_input": "Так сколько стоит подключение?",
                "turn_relation": "continuation",
                "is_repeat_like": True,
                "dialog_state": dialog_state,
            }
        )

    assert result["decision"] == "RESPOND"
    assert result["dialog_state"]["repeat_count"] == 3
    assert result["dialog_state"]["handoff_confirmation_pending"] is True


@pytest.mark.asyncio
async def test_policy_engine_filters_risk_features_by_allowlist():
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
                "intent": "support",
                "topic": "support",
                "features": {"Axole": 1.0},
                "user_input": "Что такое Axole?",
                "turn_relation": "new_topic",
                "dialog_state": {"repeat_count": 0, "lifecycle": "warm"},
            }
        )

    trace = [
        call
        for call in logger.info.call_args_list
        if call.args and call.args[0] == "Policy routing trace"
    ][-1]
    assert result["decision"] == "LLM_GENERATE"
    assert trace.kwargs["extra"]["risk_features"] == []
    assert trace.kwargs["extra"]["unrecognized_feature_keys"] == ["Axole"]


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


@pytest.mark.asyncio
async def test_policy_engine_sets_conversational_generation_mode_for_smalltalk():
    node = create_policy_engine_node()

    result = await node(
        {
            "domain": "smalltalk",
            "intent": "other",
            "topic": "other",
            "turn_relation": "new_topic",
            "user_input": "???????",
            "dialog_state": {"repeat_count": 0},
        }
    )

    assert result["decision"] == "LLM_GENERATE"
    assert result["generation_mode"] == "CONVERSATIONAL_RESPONSE"
    assert result["knowledge_retrieval_status"] == "skipped"
    assert result["should_search_kb"] is False
    assert result["should_generate_answer"] is True


@pytest.mark.asyncio
async def test_policy_engine_overwrites_stale_generation_mode_for_factual_turn():
    node = create_policy_engine_node()

    result = await node(
        {
            "domain": "business",
            "intent": "other",
            "topic": "product",
            "turn_relation": "new_topic",
            "user_input": "??? ????? Axole?",
            "generation_mode": "CONVERSATIONAL_RESPONSE",
            "tool_result": {"text": "stale"},
            "tool_execution_status": "succeeded",
            "dialog_state": {"repeat_count": 0},
        }
    )

    assert result["decision"] == "LLM_GENERATE"
    assert result["generation_mode"] == "KNOWLEDGE_ANSWER"


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["greeting", "out_of_domain", "ambiguous"])
async def test_policy_engine_template_domains_clear_generation_mode(domain):
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
                "domain": domain,
                "intent": "other",
                "generation_mode": "TOOL_RESULT_RESPONSE",
                "tool_name": "stale.tool",
                "tool_result": {"stale": True},
                "tool_execution_status": "succeeded",
                "knowledge_chunks": [{"id": "stale", "content": "old"}],
                "knowledge_retrieval_status": "retrieved",
            }
        )

    assert result["decision"] == "RESPOND_TEMPLATE"
    assert result["generation_mode"] is None
    assert result["should_search_kb"] is False
    assert result["should_generate_answer"] is False
    assert result["tool_name"] is None
    assert result["tool_args"] is None
    assert result["tool_result"] is None
    assert result["tool_execution_status"] is None
    assert result["knowledge_chunks"] == []
    assert result["tool_result"] is None
    assert result["tool_execution_status"] is None
