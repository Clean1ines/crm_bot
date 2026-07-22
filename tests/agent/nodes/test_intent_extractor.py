from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.intent_extractor import create_intent_extractor_node
from src.domain.runtime.tool_execution import ToolExecutionOutcome
from src.agent.nodes.kb_search import create_kb_search_node


@pytest.mark.asyncio
async def test_intent_extractor_returns_empty_when_no_input():
    llm = AsyncMock()
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.intent_extractor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({})

    assert result == {}
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_intent_extractor_parses_json_block_into_state_patch():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content="""```json\n{"intent":"support","cta":"none","features":{"crm":0.8},"topic":"support","cta_hint":null,"emotion":"negative","is_repeat_like":true}\n```"""
        )
    )
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.intent_extractor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"user_input": "help"})

    assert result["intent"] == "support"
    assert result["features"] == {}
    assert result["is_repeat_like"] is True


@pytest.mark.asyncio
async def test_intent_extractor_downgrades_false_handoff_for_manager_information_question(
    monkeypatch,
):
    monkeypatch.setenv("RAG_DEBUG", "true")
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content="""{"domain":"business","intent":"handoff_request","cta":"call_manager","features":{"handoff":0.9},"topic":"handoff","cta_hint":null,"emotion":"neutral","is_repeat_like":false,"should_search_kb":false,"should_generate_answer":false,"should_offer_manager":true}"""
        )
    )
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.intent_extractor.logger") as logger,
    ):
        result = await node({"user_input": "Как менеджер работает с обращениями?"})

    assert result["intent"] != "handoff_request"
    assert result["topic"] != "handoff"
    assert result["cta"] == "none"
    assert result["should_search_kb"] is True
    assert result["should_generate_answer"] is True
    assert result["should_offer_manager"] is False

    trace = [
        call
        for call in logger.info.call_args_list
        if call.args and call.args[0] == "Intent extraction trace"
    ][-1]
    assert trace.kwargs["extra"]["handoff_intent_downgraded"] is True
    assert (
        trace.kwargs["extra"]["handoff_intent_downgrade_reason"]
        == "mention_without_explicit_request"
    )


@pytest.mark.asyncio
async def test_intent_extractor_keeps_advisory_manager_offer():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content="""{"domain":"business","intent":"support","cta":"call_manager","features":{},"topic":"support","cta_hint":null,"emotion":"neutral","is_repeat_like":false,"should_search_kb":true,"should_generate_answer":true,"should_offer_manager":true}"""
        )
    )
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.intent_extractor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"user_input": "Можно ли получить персональный расчёт?"})

    assert result["intent"] == "support"
    assert result["topic"] == "support"
    assert result["cta"] == "call_manager"
    assert result["should_search_kb"] is True
    assert result["should_generate_answer"] is True
    assert result["should_offer_manager"] is True


@pytest.mark.asyncio
async def test_intent_extractor_keeps_explicit_handoff_request():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content="""{"domain":"business","intent":"handoff_request","cta":"call_manager","features":{"handoff":0.9},"topic":"handoff","cta_hint":null,"emotion":"neutral","is_repeat_like":false,"should_search_kb":false,"should_generate_answer":false,"should_offer_manager":true}"""
        )
    )
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.intent_extractor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"user_input": "Позови менеджера"})

    assert result["intent"] == "handoff_request"
    assert result["topic"] == "handoff"
    assert result["cta"] == "call_manager"


@pytest.mark.asyncio
async def test_intent_extractor_normalizes_short_affirmative_reply_using_context():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content="""{"intent":"other","cta":"none","features":{},"topic":"other","cta_hint":null,"emotion":"neutral","is_repeat_like":false}"""
        )
    )
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.intent_extractor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "user_input": "да",
                "topic": "pricing",
                "cta": "call_manager",
                "history": [
                    {
                        "role": "assistant",
                        "content": "Если удобно, могу подключить менеджера.",
                    }
                ],
            }
        )

    assert result["intent"] == "sales"
    assert result["topic"] == "pricing"
    assert result["cta"] == "call_manager"


@pytest.mark.asyncio
async def test_intent_extractor_resolves_short_affirmative_from_persisted_cta_without_rewriting_input():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content="""{"intent":"other","cta":"none","features":{},"topic":"other","cta_hint":null,"emotion":"neutral","is_repeat_like":false}"""
        )
    )
    node = create_intent_extractor_node(llm=llm)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    state = {
        "user_input": "Да",
        "topic": "pricing",
        "cta": "none",
        "dialog_state": {
            "last_intent": "pricing",
            "last_cta": "call_manager",
            "last_topic": "pricing",
            "repeat_count": 1,
            "lead_status": "warm",
            "lifecycle": "warm",
        },
    }
    with patch(
        "src.agent.nodes.intent_extractor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(state)

    assert state["user_input"] == "Да"
    assert result["intent"] == "sales"
    assert result["topic"] == "pricing"
    assert result["cta"] == "call_manager"
    assert result["should_search_kb"] is False


@pytest.mark.asyncio
async def test_production_continuation_yes_uses_resolved_query_not_literal_yes():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content="""{"intent":"other","cta":"none","features":{},"topic":"other","cta_hint":null,"emotion":"neutral","is_repeat_like":false}"""
        )
    )
    intent_node = create_intent_extractor_node(llm=llm)

    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    kb_node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Да",
        "dialog_state": {
            "last_cta": "continue_explanation",
            "last_topic": "product",
            "lead_status": "warm",
            "lifecycle": "warm",
        },
    }
    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
    ):
        intent_patch = await intent_node(state)
        assert state["user_input"] == "Да"
        assert intent_patch["turn_relation"] == "continuation"
        assert intent_patch["cta"] == "continue_explanation"
        assert intent_patch["should_search_kb"] is True

        await kb_node({**state, **intent_patch})

    called_args = tool_registry.execute.await_args.args[1]
    assert called_args["query"] != "Да"
    assert "продукт" in called_args["query"]


@pytest.mark.asyncio
async def test_stale_continuation_query_cannot_leak_into_next_independent_turn():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            SimpleNamespace(
                content="""{"intent":"other","cta":"none","features":{},"topic":"other","cta_hint":null,"emotion":"neutral","is_repeat_like":false}"""
            ),
            SimpleNamespace(
                content="""{"intent":"pricing","cta":"none","features":{},"topic":"pricing","cta_hint":null,"emotion":"neutral","is_repeat_like":false,"turn_relation":"new_topic"}"""
            ),
        ]
    )
    intent_node = create_intent_extractor_node(llm=llm)

    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    kb_node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    first_state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Да",
        "dialog_state": {
            "last_cta": "continue_explanation",
            "last_topic": "product",
        },
    }
    second_state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Сколько это стоит?",
        "knowledge_query": "подробнее как работает продукт и его возможности",
        "turn_relation": "new_topic",
        "cta": "none",
        "topic": "pricing",
    }
    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
    ):
        first_patch = await intent_node(first_state)
        assert first_patch["knowledge_query"] != "Да"
        await kb_node({**first_state, **first_patch})

        second_patch = await intent_node(second_state)
        assert second_patch["knowledge_query"] is None
        await kb_node({**second_state, **second_patch})

    second_call_args = tool_registry.execute.await_args_list[1].args[1]
    assert second_call_args["query"] == "Сколько это стоит?"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_input", "expected_query_part"),
    (
        ("Да", "подробнее как работает продукт"),
        ("Yes", "more details about how the product works"),
        ("Ja", "weitere Einzelheiten zur Funktionsweise"),
        ("Sí", "más detalles sobre cómo funciona"),
    ),
)
async def test_continuation_search_query_is_localized_for_short_reply(
    user_input,
    expected_query_part,
):
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content="""{"intent":"other","cta":"none","features":{},"topic":"other","cta_hint":null,"emotion":"neutral","is_repeat_like":false}"""
        )
    )
    intent_node = create_intent_extractor_node(llm=llm)

    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    kb_node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": user_input,
        "dialog_state": {
            "last_cta": "continue_explanation",
            "last_topic": "product",
        },
    }
    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
    ):
        intent_patch = await intent_node(state)
        await kb_node({**state, **intent_patch})

    called_args = tool_registry.execute.await_args.args[1]
    assert called_args["query"] != user_input
    assert expected_query_part in called_args["query"]
