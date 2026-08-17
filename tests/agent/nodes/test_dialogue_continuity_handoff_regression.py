import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.intent_extractor import create_intent_extractor_node
from src.agent.nodes.kb_search import create_kb_search_node
from src.agent.nodes.policy_engine import create_policy_engine_node
from src.agent.nodes.rules import rules_node
from src.domain.runtime.knowledge_search import KnowledgeSearchContext
from src.domain.runtime.persistence import PersistenceContext
from src.domain.runtime.tool_execution import ToolExecutionOutcome


class SequenceIntentLlm:
    async def ainvoke(self, messages):
        prompt = messages[0][1]
        user_input = prompt.split("Сообщение пользователя:", 1)[1].split(
            "Контекст диалога:",
            1,
        )[0]
        if "Что такое менеджерский контур?" in user_input:
            payload = {
                "domain": "business",
                "turn_relation": "new_topic",
                "intent": "support",
                "cta": "call_manager",
                "features": {},
                "topic": "support",
                "emotion": "neutral",
                "should_search_kb": True,
                "should_generate_answer": True,
                "should_offer_manager": True,
                "knowledge_query": None,
                "current_subject": "менеджерский контур",
                "repeat_relation": "none",
                "dissatisfaction": False,
                "memory_candidates": [],
            }
        elif "а как его подключить?" in user_input:
            payload = {
                "domain": "business",
                "turn_relation": "continuation",
                "intent": "support",
                "cta": "call_manager",
                "features": {},
                "topic": "integration",
                "emotion": "neutral",
                "should_search_kb": True,
                "should_generate_answer": True,
                "should_offer_manager": True,
                "knowledge_query": "Подключение PDF",
                "current_subject": "PDF",
                "repeat_relation": "clarification",
                "dissatisfaction": False,
                "memory_candidates": [],
            }
        else:
            payload = {
                "domain": "business",
                "turn_relation": "new_topic",
                "intent": "support",
                "cta": "none",
                "features": {},
                "topic": "support",
                "emotion": "neutral",
                "should_search_kb": True,
                "should_generate_answer": True,
                "should_offer_manager": False,
                "knowledge_query": None,
                "current_subject": "форматы документов",
                "repeat_relation": "none",
                "dissatisfaction": False,
                "memory_candidates": [],
            }
        return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))


async def _passthrough(_name, impl, state, **_kwargs):
    return await impl(state)


@pytest.mark.asyncio
async def test_production_dialogue_continuity_sequence_routes_followup_to_current_subject():
    intent_node = create_intent_extractor_node(llm=SequenceIntentLlm())
    policy_node = create_policy_engine_node(event_repo=None)
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(
            payload={
                "results": [
                    {
                        "id": "manager-contour",
                        "score": 0.91,
                        "content": "Менеджерский контур подключается в настройках проекта.",
                    }
                ]
            }
        )
    )
    kb_node = create_kb_search_node(tool_registry=tool_registry)

    with (
        patch(
            "src.agent.nodes.rules.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
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
    ):
        pdf_rule = await rules_node({"user_input": "А PDF?"})
        assert pdf_rule["decision"] == "PROCEED_TO_LLM"

        base_state = {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "lifecycle": "active_client",
            "user_input": "Что такое менеджерский контур?",
            "history": [
                {"role": "user", "content": "Какие форматы документов есть?"},
                {"role": "assistant", "content": "Поддерживаются PDF и DOCX."},
                {"role": "user", "content": "А PDF?"},
                {"role": "assistant", "content": "Да, PDF поддерживается."},
            ],
            "conversation_context": {"current_subject": "форматы документов"},
            "dialog_state": {"last_cta": None, "last_topic": "support"},
        }
        intent_patch = await intent_node(base_state)
        manager_state = {**base_state, **intent_patch}
        assert manager_state["turn_relation"] == "new_topic"
        assert manager_state["current_subject"] == "менеджерский контур"
        assert manager_state["cta"] == "none"
        assert manager_state["should_offer_manager"] is False

        policy_patch = await policy_node(manager_state)
        assert policy_patch["decision"] == "LLM_GENERATE"
        assert policy_patch["cta"] == "none"
        assert policy_patch["should_offer_manager"] is False

        persisted = PersistenceContext.from_state(
            {
                **manager_state,
                **policy_patch,
                "response_text": "Менеджерский контур — это функция для работы с обращениями.",
                "model_answerability": "supported",
                "supporting_entry_ids": ["manager-contour"],
            }
        )
        assert persisted.state_payload is not None
        conversation_context = persisted.state_payload["conversation_context"]
        assert conversation_context["current_subject"] == "менеджерский контур"

        followup_state = {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "lifecycle": "active_client",
            "user_input": "а как его подключить?",
            "history": [
                *base_state["history"],
                {"role": "user", "content": "Что такое менеджерский контур?"},
                {
                    "role": "assistant",
                    "content": "Менеджерский контур — это функция для работы с обращениями.",
                },
            ],
            "conversation_context": conversation_context,
            "dialog_state": policy_patch["dialog_state"],
        }
        followup_intent = await intent_node(followup_state)
        assert followup_intent["turn_relation"] == "continuation"
        assert followup_intent["current_subject"] == "менеджерский контур"
        assert "менеджерск" in str(followup_intent["knowledge_query"]).lower()
        assert "pdf" not in str(followup_intent["knowledge_query"]).lower()
        assert followup_intent["knowledge_query_source"] == "model_contextual"
        assert followup_intent["cta"] == "none"
        assert followup_intent["should_offer_manager"] is False

        followup_policy = await policy_node({**followup_state, **followup_intent})
        assert followup_policy["decision"] == "LLM_GENERATE"
        assert followup_policy["knowledge_query"] == followup_intent["knowledge_query"]
        assert followup_policy["knowledge_query_source"] == "model_contextual"
        assert followup_policy["should_offer_manager"] is False

        search_context = KnowledgeSearchContext.from_state(
            {**followup_state, **followup_intent, **followup_policy}
        )
        assert search_context.resolved_query_used is True
        assert search_context.query_source == "model_contextual"

        await kb_node({**followup_state, **followup_intent, **followup_policy})

    called_args = tool_registry.execute.await_args.args[1]
    assert "менеджерск" in called_args["query"].lower()
    assert "pdf" not in called_args["query"].lower()
