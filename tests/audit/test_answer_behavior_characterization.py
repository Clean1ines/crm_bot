from dataclasses import dataclass, field
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.nodes.escalate import create_escalate_node
from src.agent.nodes.intent_extractor import create_intent_extractor_node
from src.agent.nodes.kb_search import create_kb_search_node
from src.agent.nodes.persist import create_persist_node
from src.agent.nodes.policy_engine import create_policy_engine_node
from src.agent.nodes.responder import create_responder_node
from src.agent.nodes.response_generator import create_response_generator_node
from src.agent.nodes.rules import rules_node
from src.agent.nodes.template_response import template_response_node


PROJECT_ID = "11111111-1111-1111-1111-111111111111"
THREAD_ID = "22222222-2222-2222-2222-222222222222"
CLIENT_ID = "33333333-3333-3333-3333-333333333333"


def _payload(
    *,
    intent: str = "sales",
    topic: str = "product",
    cta: str = "none",
    domain: str = "business",
    turn_relation: str = "new_topic",
    should_search_kb: bool = True,
    should_generate_answer: bool = True,
    emotion: str = "neutral",
    features: dict[str, float] | None = None,
) -> dict[str, object]:
    return {
        "domain": domain,
        "turn_relation": turn_relation,
        "intent": intent,
        "cta": cta,
        "features": features or {},
        "topic": topic,
        "cta_hint": None,
        "emotion": emotion,
        "is_repeat_like": False,
        "should_search_kb": should_search_kb,
        "should_generate_answer": should_generate_answer,
        "should_offer_manager": False,
    }


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    user_input: str
    expected_business_outcome: str
    intent_payload: dict[str, object] | None = None
    response_text: str = "Ответ по базе знаний."
    initial_state: dict[str, object] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)
    user_memory: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    kb_results: list[dict[str, object]] = field(
        default_factory=lambda: [
            {"id": "entry-1", "score": 0.9, "content": "Факт из базы знаний."}
        ]
    )
    kb_exception: Exception | None = None
    intent_exception: Exception | None = None
    generation_exception: Exception | None = None


class FakeLLM:
    def __init__(
        self,
        payload: dict[str, object] | None = None,
        *,
        text: str = "Ответ по базе знаний.",
        exc: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.text = text
        self.exc = exc
        self.ainvoke = AsyncMock(side_effect=self._ainvoke)

    async def _ainvoke(self, _messages):
        if self.exc is not None:
            raise self.exc
        if self.payload is not None:
            return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))
        return SimpleNamespace(content=self.text)


class FakeToolRegistry:
    def __init__(
        self,
        *,
        kb_results: list[dict[str, object]],
        kb_exception: Exception | None = None,
    ) -> None:
        self.kb_results = kb_results
        self.kb_exception = kb_exception
        self.calls: list[dict[str, object]] = []

    async def execute(self, name, args, context=None):
        self.calls.append({"name": name, "args": dict(args), "context": context or {}})
        if name == "search_knowledge":
            if self.kb_exception is not None:
                raise self.kb_exception
            return {"results": self.kb_results}
        if name == "telegram.send_message":
            return {"ok": True, "message_id": len(self.calls)}
        return {"ok": True, "text": "tool ok"}


async def _passthrough(_name, impl, state, **_kwargs):
    return await impl(state)


async def run_scenario(scenario: Scenario) -> dict[str, object]:
    tool_registry = FakeToolRegistry(
        kb_results=scenario.kb_results,
        kb_exception=scenario.kb_exception,
    )
    intent_llm = FakeLLM(
        scenario.intent_payload or _payload(),
        exc=scenario.intent_exception,
    )
    response_llm = FakeLLM(
        text=scenario.response_text, exc=scenario.generation_exception
    )

    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(return_value={"ticket_id": "ticket-1"})

    thread_message_repo = MagicMock()
    thread_message_repo.add_message = AsyncMock()
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.save_state_json = AsyncMock()
    thread_runtime_state_repo.update_analytics = AsyncMock()
    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(return_value=None)
    event_repo = MagicMock()
    event_repo.append = AsyncMock()
    memory_repo = MagicMock()
    memory_repo.set = AsyncMock()

    intent_node = create_intent_extractor_node(llm=intent_llm)
    policy_node = create_policy_engine_node(event_repo=event_repo)
    kb_node = create_kb_search_node(tool_registry)
    response_node = create_response_generator_node(
        llm=response_llm,
        model_name="llama-3.3-70b-versatile",
    )
    escalate_node = create_escalate_node(
        thread_lifecycle_repo,
        queue_repo,
        ticket_create_tool,
    )
    responder_node = create_responder_node(
        tool_registry,
        thread_message_repo=thread_message_repo,
    )
    persist_node = create_persist_node(
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        thread_read_repo=thread_read_repo,
        event_repo=event_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    state: dict[str, Any] = {
        "project_id": PROJECT_ID,
        "thread_id": THREAD_ID,
        "client_id": CLIENT_ID,
        "chat_id": 123,
        "user_input": scenario.user_input,
        "history": list(scenario.history),
        "user_memory": dict(scenario.user_memory),
        "project_configuration": {"settings": {"target_language": "ru"}},
        "conversation_summary": "",
        "requires_human": False,
        **scenario.initial_state,
    }
    nodes: list[str] = []

    async def apply(name: str, node):
        nodes.append(name)
        patch = await node(state)
        state.update(dict(patch or {}))

    await apply("rules", rules_node)
    if state.get("decision") == "PROCEED_TO_LLM":
        await apply("intent_extractor", intent_node)
        await apply("policy_engine", policy_node)

    if state.get("decision") == "RESPOND_TEMPLATE":
        await apply("template_response", template_response_node)
    elif state.get("decision") == "LLM_GENERATE":
        await apply("kb_search", kb_node)
        await apply("response_generator", response_node)
    elif state.get("decision") in {"ESCALATE", "ESCALATE_TO_HUMAN"}:
        await apply("escalate", escalate_node)

    await apply("responder", responder_node)
    await apply("persist", persist_node)

    telegram_messages = [
        call["args"]["text"]
        for call in tool_registry.calls
        if call["name"] == "telegram.send_message"
    ]
    search_queries = [
        call["args"]["query"]
        for call in tool_registry.calls
        if call["name"] == "search_knowledge"
    ]
    saved_states = [
        call.args[1]
        for call in thread_runtime_state_repo.save_state_json.await_args_list
    ]
    memory_writes = [
        {
            "key": call.kwargs["key"],
            "value": call.kwargs["value"],
            "type": call.kwargs["type_"],
        }
        for call in memory_repo.set.await_args_list
    ]
    return {
        "name": scenario.name,
        "expected_business_outcome": scenario.expected_business_outcome,
        "nodes": nodes,
        "final_response": telegram_messages[-1] if telegram_messages else None,
        "requires_human": state.get("requires_human"),
        "dialog_state": state.get("dialog_state"),
        "memory_writes": memory_writes,
        "tool_calls": tool_registry.calls,
        "search_queries": search_queries,
        "saved_state": saved_states[-1] if saved_states else None,
    }


SCENARIOS = [
    Scenario("first_product_question", "Что умеет сервис?", "Explain product value."),
    Scenario(
        "yes_after_continuation",
        "Да",
        "Continue previous product explanation, not literal yes search.",
        initial_state={
            "lifecycle": "active_client",
            "dialog_state": {
                "last_cta": "continue_explanation",
                "last_topic": "product",
                "lifecycle": "active_client",
                "lead_status": "active_client",
            },
        },
    ),
    Scenario(
        "no_after_continuation",
        "Нет",
        "Consume continuation CTA and close neutrally.",
        initial_state={
            "dialog_state": {
                "last_cta": "continue_explanation",
                "last_topic": "product",
            }
        },
    ),
    Scenario(
        "new_pricing_question_instead_of_continuation",
        "Сколько это стоит?",
        "Expire continuation and answer pricing.",
        intent_payload=_payload(intent="pricing", topic="pricing"),
        initial_state={
            "dialog_state": {
                "last_cta": "continue_explanation",
                "last_topic": "product",
            }
        },
    ),
    Scenario(
        "exact_repeat_question",
        "Сколько стоит?",
        "Treat exact repeat carefully.",
        intent_payload=_payload(intent="pricing", topic="pricing"),
        initial_state={
            "dialog_state": {
                "last_intent": "pricing",
                "last_topic": "pricing",
                "repeat_count": 1,
            }
        },
    ),
    Scenario(
        "same_topic_different_question",
        "Можно ли платить помесячно?",
        "Pricing follow-up, not failed repeat.",
        intent_payload=_payload(intent="pricing", topic="pricing"),
        initial_state={
            "dialog_state": {
                "last_intent": "pricing",
                "last_topic": "pricing",
                "repeat_count": 1,
            }
        },
    ),
    Scenario(
        "third_integration_clarification",
        "А сообщения синхронизируются?",
        "Continue integration detail unless genuinely stuck.",
        intent_payload=_payload(
            intent="sales", topic="integration", features={"topic": "integration"}
        ),
        initial_state={
            "dialog_state": {
                "last_intent": "sales",
                "last_topic": "integration",
                "repeat_count": 2,
            }
        },
    ),
    Scenario(
        "three_failed_repeats",
        "Сколько стоит?",
        "Offer human help after repeated failed answers.",
        intent_payload=_payload(intent="pricing", topic="pricing"),
        initial_state={
            "dialog_state": {
                "last_intent": "pricing",
                "last_topic": "pricing",
                "repeat_count": 2,
            }
        },
    ),
    Scenario(
        "explicit_manager_immediate", "Позовите менеджера", "Escalate immediately."
    ),
    Scenario(
        "explicit_manager_after_long_dialog",
        "Хочу оператора",
        "Escalate with context.",
        history=[
            {"role": "user", "content": "Вопрос 1"},
            {"role": "assistant", "content": "Ответ 1"},
        ]
        * 5,
    ),
    Scenario(
        "word_human_false_positive",
        "Поддерживает ли система human-in-the-loop?",
        "Answer product question, not handoff.",
    ),
    Scenario(
        "word_manager_domain_question",
        "Как менеджер распределяет обращения?",
        "Answer product question, not handoff.",
        intent_payload=_payload(),
    ),
    Scenario("anger_without_handoff", "Ваш сервис бесит", "Ask before handoff."),
    Scenario(
        "anger_handoff_confirmed",
        "Да",
        "Escalate after anger confirmation.",
        initial_state={"dialog_state": {"handoff_confirmation_pending": True}},
    ),
    Scenario(
        "anger_handoff_declined",
        "Нет",
        "Do not escalate after decline.",
        initial_state={"dialog_state": {"handoff_confirmation_pending": True}},
    ),
    Scenario(
        "new_question_instead_of_handoff_confirmation",
        "А сколько стоит?",
        "Clear confirmation and answer new question.",
        intent_payload=_payload(intent="pricing", topic="pricing"),
        initial_state={"dialog_state": {"handoff_confirmation_pending": True}},
    ),
    Scenario(
        "empty_kb_result",
        "Что умеет сервис?",
        "Answer honestly with no evidence.",
        kb_results=[],
    ),
    Scenario(
        "retrieval_exception",
        "Что умеет сервис?",
        "Degrade to generation with empty evidence.",
        kb_exception=RuntimeError("kb down"),
    ),
    Scenario(
        "generation_exception",
        "Что умеет сервис?",
        "Show technical failure fallback.",
        generation_exception=RuntimeError("llm down"),
    ),
    Scenario(
        "technical_replay",
        "Что умеет сервис?",
        "Create/queue technical incident after repeat failure.",
        generation_exception=RuntimeError("llm down"),
        initial_state={"technical_failure_count": 1},
    ),
    Scenario(
        "return_to_old_topic",
        "Вернёмся к цене",
        "Resume pricing context.",
        intent_payload=_payload(intent="pricing", topic="pricing"),
        initial_state={
            "dialog_state": {
                "last_intent": "sales",
                "last_topic": "integration",
                "repeat_count": 1,
            }
        },
    ),
    Scenario(
        "user_already_gave_details",
        "У нас 5 менеджеров и CRM Bitrix24",
        "Use supplied details.",
        intent_payload=_payload(
            intent="sales", topic="integration", features={"topic": "integration"}
        ),
    ),
    Scenario(
        "multiple_questions_one_message",
        "Что умеет сервис? Сколько стоит?",
        "Answer both or split upstream.",
        intent_payload=_payload(intent="pricing", topic="pricing"),
    ),
    Scenario(
        "short_yes_without_pending_cta",
        "Да",
        "Do not invent action or specific query.",
        intent_payload=_payload(intent="other", topic="other"),
    ),
    Scenario(
        "manager_after_failed_answers",
        "Позовите менеджера",
        "Escalate immediately after failures.",
        initial_state={
            "dialog_state": {
                "last_intent": "pricing",
                "last_topic": "pricing",
                "repeat_count": 3,
            }
        },
    ),
]


@pytest.mark.asyncio
async def test_business_answer_flow_characterization_scenarios_execute():
    outcomes = {scenario.name: await run_scenario(scenario) for scenario in SCENARIOS}

    assert len(outcomes) == 25
    assert outcomes["explicit_manager_immediate"]["nodes"] == [
        "rules",
        "escalate",
        "responder",
        "persist",
    ]
    assert outcomes["yes_after_continuation"]["search_queries"] != ["Да"]
    assert outcomes["yes_after_continuation"]["search_queries"][0] != "Да"
    assert (
        outcomes["generation_exception"]["saved_state"]["technical_failure_count"] == 1
    )
    assert (
        outcomes["technical_replay"]["saved_state"]["technical_incident_created"]
        is True
    )


@pytest.mark.xfail(strict=True, reason="AUDIT BUG-003: topic streak is not true repeat")
@pytest.mark.asyncio
async def test_audit_same_topic_different_question_should_not_increment_failed_repeat():
    outcome = await run_scenario(
        Scenario(
            "same_topic_different_question",
            "Можно ли платить помесячно?",
            "Pricing follow-up, not failed repeat.",
            intent_payload=_payload(intent="pricing", topic="pricing"),
            initial_state={
                "dialog_state": {
                    "last_intent": "pricing",
                    "last_topic": "pricing",
                    "repeat_count": 1,
                }
            },
        )
    )

    assert outcome["dialog_state"]["repeat_count"] == 1


@pytest.mark.asyncio
async def test_audit_human_in_the_loop_should_not_auto_escalate():
    outcome = await run_scenario(
        Scenario(
            "word_human_false_positive",
            "Поддерживает ли система human-in-the-loop?",
            "Answer product question, not handoff.",
        )
    )

    assert outcome["nodes"] != ["rules", "escalate", "responder", "persist"]
    assert "kb_search" in outcome["nodes"]


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT BUG-003: integration deepening escalates as repeat",
)
@pytest.mark.asyncio
async def test_audit_integration_deepening_should_continue_rag_not_handoff():
    outcome = await run_scenario(
        Scenario(
            "third_integration_clarification",
            "А сообщения синхронизируются?",
            "Continue integration detail unless genuinely stuck.",
            intent_payload=_payload(
                intent="sales", topic="integration", features={"topic": "integration"}
            ),
            initial_state={
                "dialog_state": {
                    "last_intent": "sales",
                    "last_topic": "integration",
                    "repeat_count": 2,
                }
            },
        )
    )

    assert "kb_search" in outcome["nodes"]
