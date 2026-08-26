import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.nodes.intent_extractor import create_intent_extractor_node
from src.agent.nodes.policy_engine import create_policy_engine_node
from src.domain.runtime.policy.handoff_request import is_explicit_handoff_request


def _handoff_payload() -> dict[str, object]:
    return {
        "domain": "business",
        "turn_relation": "new_topic",
        "intent": "handoff_request",
        "cta": "call_manager",
        "features": {},
        "topic": "handoff",
        "cta_hint": None,
        "emotion": "neutral",
        "is_repeat_like": False,
        "should_search_kb": False,
        "should_generate_answer": False,
        "should_offer_manager": True,
        "knowledge_query": None,
        "current_subject": "менеджер",
        "repeat_relation": "none",
        "dissatisfaction": False,
        "memory_candidates": [],
    }


async def _passthrough(_name, impl, state, **_kwargs):
    return await impl(state)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input",
    [
        "Менеджера мне",
        "Я хочу с человеком",
        "Можно живого человека сюда",
    ],
)
async def test_semantic_handoff_missed_by_rules_routes_to_real_escalation(user_input):
    # These phrases intentionally exercise the LLM fallback rather than the
    # deterministic fast-path regexes.
    assert is_explicit_handoff_request(user_input) is False

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(_handoff_payload(), ensure_ascii=False)
        )
    )
    intent_node = create_intent_extractor_node(llm=llm)
    policy_node = create_policy_engine_node(event_repo=None)

    with patch(
        "src.agent.nodes.intent_extractor.log_node_execution",
        AsyncMock(side_effect=_passthrough),
    ):
        intent_patch = await intent_node({"user_input": user_input})

    assert intent_patch["intent"] == "handoff_request"
    assert intent_patch["topic"] == "handoff"
    assert intent_patch["cta"] == "call_manager"
    assert intent_patch["resolved_cta"] == "call_manager"
    assert intent_patch["resolved_cta_reply"] == "affirmative"
    assert intent_patch["should_search_kb"] is False
    assert intent_patch["should_generate_answer"] is False
    assert intent_patch["normalization_flags"]["semantic_handoff_restored"] is True

    state = {
        "thread_id": "thread-1",
        "project_id": "project-1",
        "user_input": user_input,
        "lifecycle": "cold",
        "dialog_state": {
            "last_intent": "support",
            "last_cta": None,
            "last_topic": "support",
            "repeat_count": 0,
            "lead_status": "cold",
            "lifecycle": "cold",
            "handoff_confirmation_pending": False,
        },
        **intent_patch,
    }
    with patch(
        "src.agent.nodes.policy_engine.log_node_execution",
        AsyncMock(side_effect=_passthrough),
    ):
        policy_patch = await policy_node(state)

    assert policy_patch["decision"] == "ESCALATE"
    assert policy_patch["requires_human"] is True
    assert policy_patch["should_search_kb"] is False
    assert policy_patch["should_generate_answer"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input",
    [
        "Что такое менеджерский контур?",
        "Как работает handoff?",
        "Можно ли настроить менеджерский бот?",
    ],
)
async def test_semantic_handoff_does_not_restore_information_questions(user_input):
    # Simulate a false-positive model classification. Informational questions
    # about the handoff mechanism must remain knowledge questions.
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(_handoff_payload(), ensure_ascii=False)
        )
    )
    intent_node = create_intent_extractor_node(llm=llm)

    with patch(
        "src.agent.nodes.intent_extractor.log_node_execution",
        AsyncMock(side_effect=_passthrough),
    ):
        result = await intent_node({"user_input": user_input})

    assert result["intent"] == "support"
    assert result["topic"] == "support"
    assert result["cta"] == "none"
    assert result["should_search_kb"] is True
    assert result["should_generate_answer"] is True
    assert result["should_offer_manager"] is False
    assert result["normalization_flags"]["handoff_intent_downgraded"] is True
