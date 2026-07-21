import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.escalate import create_escalate_node
from src.agent.nodes.intent_extractor import create_intent_extractor_node
from src.agent.nodes.kb_search import create_kb_search_node
from src.agent.nodes.policy_engine import create_policy_engine_node
from src.agent.nodes.response_generator import create_response_generator_node
from src.domain.runtime.persistence import PersistenceContext


PROJECT_ID = "11111111-1111-1111-1111-111111111111"
THREAD_ID = "22222222-2222-2222-2222-222222222222"
CLIENT_ID = "33333333-3333-3333-3333-333333333333"


class FakeLLM:
    def __init__(
        self,
        *,
        payload: dict[str, object] | None = None,
        text: str = "Ответ по базе знаний.",
    ) -> None:
        self.payload = payload
        self.text = text
        self.ainvoke = AsyncMock(side_effect=self._ainvoke)

    async def _ainvoke(self, _messages):
        if self.payload is not None:
            return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))
        return SimpleNamespace(content=self.text)


class FakeToolRegistry:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, name, args, context=None):
        self.calls.append({"name": name, "args": dict(args), "context": context or {}})
        if name == "search_knowledge":
            return {
                "results": [
                    {
                        "id": "entry-1",
                        "score": 0.9,
                        "content": "Axole автоматизирует ответы клиентам.",
                    }
                ]
            }
        if name == "telegram.send_message":
            return {"ok": True, "message_id": len(self.calls)}
        return {"ok": True}


def _intent_payload() -> dict[str, object]:
    return {
        "domain": "business",
        "turn_relation": "unknown",
        "intent": "other",
        "cta": "none",
        "features": {},
        "topic": "other",
        "cta_hint": None,
        "emotion": "neutral",
        "is_repeat_like": False,
        "should_search_kb": True,
        "should_generate_answer": True,
        "should_offer_manager": False,
    }


async def _passthrough(_name, impl, state, **_kwargs):
    return await impl(state)


@pytest.mark.asyncio
async def test_full_flow_continuation_yes_uses_resolved_query_and_consumes_cta():
    state = {
        "project_id": PROJECT_ID,
        "thread_id": THREAD_ID,
        "client_id": CLIENT_ID,
        "chat_id": 123,
        "user_input": "Да",
        "lifecycle": "active_client",
        "dialog_state": {
            "last_cta": "continue_explanation",
            "last_topic": "product",
            "lifecycle": "active_client",
            "lead_status": "active_client",
        },
        "project_configuration": {"settings": {"target_language": "ru"}},
    }
    intent_node = create_intent_extractor_node(llm=FakeLLM(payload=_intent_payload()))
    policy_node = create_policy_engine_node()
    registry = FakeToolRegistry()
    kb_node = create_kb_search_node(registry)
    response_node = create_response_generator_node(
        llm=FakeLLM(text="Вот подробнее: сервис подключается к базе знаний."),
        model_name="llama-3.3-70b-versatile",
    )

    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
    ):
        state.update(await intent_node(state))
        assert state["cta"] == "continue_explanation"
        assert state["knowledge_query"] != "Да"

        state.update(await policy_node(state))
        assert state["decision"] == "LLM_GENERATE"
        assert state["requires_human"] is False
        assert state["cta"] == "continue_explanation"
        assert state["turn_relation"] == "continuation"

        state.update(await kb_node(state))
        state.update(await response_node(state))

    search_calls = [
        call for call in registry.calls if call["name"] == "search_knowledge"
    ]
    assert search_calls
    actual_search_query = search_calls[-1]["args"]["query"]
    assert actual_search_query != "Да"
    assert "продукт" in actual_search_query
    assert state["response_text"]

    persisted = PersistenceContext.from_state(state).normalized_dialog_state()
    assert persisted["last_cta"] is None


@pytest.mark.asyncio
async def test_full_flow_action_cta_yes_routes_to_escalation_and_consumes_cta():
    state = {
        "project_id": PROJECT_ID,
        "thread_id": THREAD_ID,
        "client_id": CLIENT_ID,
        "chat_id": 123,
        "user_input": "Да",
        "lifecycle": "active_client",
        "dialog_state": {
            "last_cta": "call_manager",
            "last_topic": "product",
            "lifecycle": "active_client",
            "lead_status": "active_client",
        },
    }
    intent_node = create_intent_extractor_node(llm=FakeLLM(payload=_intent_payload()))
    policy_node = create_policy_engine_node()

    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(return_value={"ticket_id": "ticket-1"})
    escalate_node = create_escalate_node(
        thread_lifecycle_repo,
        queue_repo,
        ticket_create_tool,
    )

    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.escalate.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
    ):
        state.update(await intent_node(state))
        assert state["cta"] == "call_manager"
        assert state["resolved_cta"] == "call_manager"

        state.update(await policy_node(state))
        assert state["decision"] == "ESCALATE"
        assert state["requires_human"] is True
        assert state["should_search_kb"] is False

        state.update(await escalate_node(state))

    ticket_create_tool.run.assert_awaited_once()
    queue_repo.enqueue.assert_any_await(
        "notify_manager",
        {
            "thread_id": THREAD_ID,
            "project_id": PROJECT_ID,
            "message": "Да",
        },
    )
    assert state["requires_human"] is True
    persisted = PersistenceContext.from_state(state).normalized_dialog_state()
    assert persisted["last_cta"] is None


@pytest.mark.asyncio
async def test_full_flow_book_consultation_yes_uses_current_manager_handoff_route():
    state = {
        "project_id": PROJECT_ID,
        "thread_id": THREAD_ID,
        "client_id": CLIENT_ID,
        "chat_id": 123,
        "user_input": "Да",
        "lifecycle": "interested",
        "dialog_state": {
            "last_cta": "book_consultation",
            "last_topic": "pricing",
            "lifecycle": "interested",
            "lead_status": "interested",
        },
    }
    intent_node = create_intent_extractor_node(llm=FakeLLM(payload=_intent_payload()))
    policy_node = create_policy_engine_node()

    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(return_value={"ticket_id": "ticket-2"})
    escalate_node = create_escalate_node(
        thread_lifecycle_repo,
        queue_repo,
        ticket_create_tool,
    )

    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.escalate.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
    ):
        state.update(await intent_node(state))
        assert state["resolved_cta"] == "book_consultation"

        state.update(await policy_node(state))
        assert state["decision"] == "ESCALATE"
        assert state["requires_human"] is True
        assert state["cta"] == "book_consultation"
        assert state["should_search_kb"] is False

        state.update(await escalate_node(state))

    ticket_create_tool.run.assert_awaited_once()
    queue_repo.enqueue.assert_any_await(
        "notify_manager",
        {
            "thread_id": THREAD_ID,
            "project_id": PROJECT_ID,
            "message": "Да",
        },
    )
    assert state["requires_human"] is True
    persisted = PersistenceContext.from_state(state).normalized_dialog_state()
    assert persisted["last_cta"] is None


@pytest.mark.asyncio
async def test_full_flow_action_cta_no_declines_without_kb_or_escalation():
    state = {
        "project_id": PROJECT_ID,
        "thread_id": THREAD_ID,
        "client_id": CLIENT_ID,
        "chat_id": 123,
        "user_input": "Нет",
        "lifecycle": "active_client",
        "dialog_state": {
            "last_cta": "call_manager",
            "last_topic": "product",
            "lifecycle": "active_client",
            "lead_status": "active_client",
        },
    }
    intent_node = create_intent_extractor_node(llm=FakeLLM(payload=_intent_payload()))
    policy_node = create_policy_engine_node()

    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
    ):
        state.update(await intent_node(state))
        state.update(await policy_node(state))

    assert state["decision"] == "RESPOND"
    assert (
        state["response_text"]
        == "Хорошо, не передаю менеджеру. Продолжу помогать здесь."
    )
    assert state["requires_human"] is False
    assert state["should_search_kb"] is False
    assert state["should_generate_answer"] is False
    persisted = PersistenceContext.from_state(state).normalized_dialog_state()
    assert persisted["last_cta"] is None
