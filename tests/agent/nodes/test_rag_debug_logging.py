import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.intent_extractor import create_intent_extractor_node
from src.agent.nodes.kb_search import create_kb_search_node
from src.agent.nodes.policy_engine import create_policy_engine_node
from src.agent.nodes.response_generator import (
    _history_tail_preview,
    create_response_generator_node,
)
from src.domain.project_plane.thread_views import ThreadRuntimeMessageView
from src.domain.runtime.tool_execution import ToolExecutionOutcome


async def _passthrough(_name, impl, state, **_kwargs):
    return await impl(state)


def _structured_content(answer: str, *, entry_id: str = "entry-1") -> str:
    evidence_ref = f"E{entry_id.removeprefix('entry-')}"
    return json.dumps(
        {
            "answerability": "supported",
            "answer": answer,
            "supporting_evidence_refs": [evidence_ref],
            "unsupported_aspects": [],
        },
        ensure_ascii=False,
    )


def _retrieved_state(content: str = "Axole helps clients.") -> dict[str, object]:
    return {
        "knowledge_chunks": [{"id": "entry-1", "score": 0.9, "content": content}],
        "knowledge_retrieval_status": "retrieved",
        "generation_mode": "KNOWLEDGE_ANSWER",
    }


@pytest.mark.asyncio
async def test_rag_debug_true_emits_retrieval_and_generation_traces(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "true")

    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(
            payload={
                "results": [
                    {
                        "id": "entry-1",
                        "score": 0.9,
                        "content": "Axole automates client replies.",
                        "method": "hybrid",
                        "entry_kind": "runtime_entry",
                        "source": "about.md",
                        "title": "About Axole",
                    }
                ]
            }
        )
    )
    kb_node = create_kb_search_node(tool_registry)

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("Axole helps."))
    )
    response_node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Что умеет сервис?",
        "decision": "LLM_GENERATE",
        "generation_mode": "KNOWLEDGE_ANSWER",
        "project_configuration": {"settings": {"target_language": "en"}},
    }

    with (
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch("src.agent.nodes.kb_search.logger") as kb_logger,
        patch("src.agent.nodes.response_generator.logger") as response_logger,
    ):
        state.update(await kb_node(state))
        state.update(await response_node(state))

    kb_trace = [
        call
        for call in kb_logger.info.call_args_list
        if call.args and call.args[0] == "RAG semantic retrieval trace"
    ]
    generation_trace = [
        call
        for call in response_logger.info.call_args_list
        if call.args and call.args[0] == "RAG generation context trace"
    ]

    assert kb_trace
    assert generation_trace
    assert kb_trace[-1].kwargs["extra"]["top_entries"][0]["id"] == "entry-1"
    assert generation_trace[-1].kwargs["extra"]["retrieved_entry_ids"] == ["entry-1"]
    assert (
        generation_trace[-1].kwargs["extra"]["prompt_entries"][0]["canonical_entry_id"]
        == "entry-1"
    )
    assert generation_trace[-1].kwargs["extra"]["generation_status"] == "success"
    assert generation_trace[-1].kwargs["extra"]["model_answerability"] == "supported"
    assert "answerability" not in generation_trace[-1].kwargs["extra"]
    assert generation_trace[-1].kwargs["extra"]["supporting_entry_ids"] == ["entry-1"]
    assert "generated_response_preview" in generation_trace[-1].kwargs["extra"]

    ordinary_logs = [
        call.args[0] for call in kb_logger.info.call_args_list if call.args
    ]
    assert "KB search start" in ordinary_logs
    assert "KB search result" in ordinary_logs


@pytest.mark.asyncio
async def test_rag_debug_true_accepts_thread_runtime_message_view_history(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "true")

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("Axole helps."))
    )
    response_node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Что умеет сервис?",
        "decision": "LLM_GENERATE",
        "history": [
            ThreadRuntimeMessageView(
                role="user",
                content="Что такое Axole?",
            )
        ],
        "project_configuration": {"settings": {"target_language": "en"}},
        **_retrieved_state(),
    }

    with (
        patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch("src.agent.nodes.response_generator.logger") as response_logger,
    ):
        result = await response_node(state)

    generation_trace = [
        call
        for call in response_logger.info.call_args_list
        if call.args and call.args[0] == "RAG generation context trace"
    ][-1]

    assert llm.ainvoke.await_count == 1
    assert result["response_text"] == "Axole helps."
    assert generation_trace.kwargs["extra"]["generation_status"] == "success"
    assert generation_trace.kwargs["extra"]["history_tail_preview"] == [
        {"role": "user", "content_preview": "Что такое Axole?"}
    ]


def test_history_tail_preview_accepts_mixed_history_items():
    class BrokenHistoryItem:
        @property
        def role(self):
            raise RuntimeError("role unavailable")

        @property
        def content(self):
            raise RuntimeError("content unavailable")

    long_content = "x" * 200

    preview = _history_tail_preview(
        [
            {"role": "user", "content": "Первое сообщение"},
            SimpleNamespace(role="assistant", content="Ответ"),
            object(),
            BrokenHistoryItem(),
            {"role": "user", "content": long_content},
        ]
    )

    assert preview[0] == {"role": "user", "content_preview": "Первое сообщение"}
    assert preview[1] == {"role": "assistant", "content_preview": "Ответ"}
    assert preview[2] == {"role": "message", "content_preview": ""}
    assert preview[3] == {"role": "message", "content_preview": ""}
    assert preview[4]["role"] == "user"
    assert len(preview[4]["content_preview"]) <= 120


@pytest.mark.asyncio
async def test_rag_debug_false_suppresses_extended_traces(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "false")

    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    kb_node = create_kb_search_node(tool_registry)

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("Axole helps."))
    )
    response_node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Что умеет сервис?",
        "decision": "LLM_GENERATE",
        "history": [SimpleNamespace(role="user", content="Что такое Axole?")],
        "project_configuration": {"settings": {"target_language": "en"}},
    }

    with (
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch("src.agent.nodes.kb_search.logger") as kb_logger,
        patch("src.agent.nodes.response_generator.logger") as response_logger,
    ):
        state.update(await kb_node(state))
        await response_node(state)

    assert llm.ainvoke.await_count == 0
    assert all(
        call.args[0] != "RAG semantic retrieval trace"
        for call in kb_logger.info.call_args_list
        if call.args
    )
    assert all(
        call.args[0] != "RAG generation context trace"
        for call in response_logger.info.call_args_list
        if call.args
    )
    assert any(
        call.args and call.args[0] == "KB search start"
        for call in kb_logger.info.call_args_list
    )


@pytest.mark.asyncio
async def test_rag_debug_true_emits_intent_and_policy_structured_traces(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "true")

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content='{"domain":"business","intent":"handoff_request","cta":"call_manager","features":{"handoff":0.9},"topic":"handoff","cta_hint":null,"emotion":"neutral","is_repeat_like":false,"should_search_kb":false,"should_generate_answer":false,"should_offer_manager":true}'
        )
    )
    intent_node = create_intent_extractor_node(llm=llm)
    policy_node = create_policy_engine_node()
    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Как менеджер работает с обращениями?",
        "lifecycle": "active_client",
        "dialog_state": {
            "last_topic": "product",
            "repeat_count": 1,
            "lead_status": "active_client",
            "lifecycle": "active_client",
        },
    }

    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch("src.agent.nodes.intent_extractor.logger") as intent_logger,
        patch("src.agent.nodes.policy_engine.logger") as policy_logger,
    ):
        state.update(await intent_node(state))
        state.update(await policy_node(state))

    intent_trace = [
        call
        for call in intent_logger.info.call_args_list
        if call.args and call.args[0] == "Intent extraction trace"
    ][-1]
    policy_trace = [
        call
        for call in policy_logger.info.call_args_list
        if call.args and call.args[0] == "Policy routing trace"
    ][-1]

    assert intent_trace.kwargs["extra"]["user_input_preview"].startswith("Как менеджер")
    assert intent_trace.kwargs["extra"]["features"] == {}
    assert intent_trace.kwargs["extra"]["unrecognized_feature_keys"] == ["handoff"]
    assert intent_trace.kwargs["extra"]["handoff_intent_downgraded"] is True
    assert policy_trace.kwargs["extra"]["input_topic"] == "support"
    assert policy_trace.kwargs["extra"]["resolved_topic"] == "support"
    assert policy_trace.kwargs["extra"]["final_decision"] == "LLM_GENERATE"
    assert policy_trace.kwargs["extra"]["handoff_signal_source"] == "none"


@pytest.mark.asyncio
async def test_rag_debug_false_keeps_safe_traces_without_content_previews(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "false")

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content='{"domain":"business","intent":"support","cta":"none","features":{"handoff":0.9},"topic":"support","cta_hint":null,"emotion":"neutral","is_repeat_like":false}'
        )
    )
    intent_node = create_intent_extractor_node(llm=llm)
    policy_node = create_policy_engine_node()
    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Как менеджер работает с обращениями?",
        "lifecycle": "active_client",
        "dialog_state": {"repeat_count": 1},
    }

    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch("src.agent.nodes.intent_extractor.logger") as intent_logger,
        patch("src.agent.nodes.policy_engine.logger") as policy_logger,
    ):
        state.update(await intent_node(state))
        await policy_node(state)

    intent_trace = [
        call
        for call in intent_logger.info.call_args_list
        if call.args and call.args[0] == "Intent extraction trace"
    ][-1]
    policy_trace = [
        call
        for call in policy_logger.info.call_args_list
        if call.args and call.args[0] == "Policy routing trace"
    ][-1]

    assert "user_input_preview" not in intent_trace.kwargs["extra"]
    assert "features" not in intent_trace.kwargs["extra"]
    assert policy_trace.kwargs["extra"]["final_decision"] == "LLM_GENERATE"


@pytest.mark.asyncio
async def test_rag_debug_true_emits_generation_failure_trace(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "true")

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("provider exploded"))
    response_node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Что умеет сервис?",
        "decision": "LLM_GENERATE",
        "knowledge_chunks": [
            {
                "id": "entry-1",
                "score": 0.8,
                "content": "A" * 600,
            }
        ],
        "knowledge_retrieval_status": "retrieved",
        "generation_mode": "KNOWLEDGE_ANSWER",
        "project_configuration": {"settings": {"target_language": "en"}},
    }

    with (
        patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=_passthrough),
        ),
        patch("src.agent.nodes.response_generator.logger") as response_logger,
    ):
        result = await response_node(state)

    generation_trace = [
        call
        for call in response_logger.info.call_args_list
        if call.args and call.args[0] == "RAG generation context trace"
    ][-1]

    assert generation_trace.kwargs["extra"]["generation_status"] == "failed"
    assert generation_trace.kwargs["extra"]["error_type"] == "RuntimeError"
    assert generation_trace.kwargs["extra"]["error_preview"] == "provider exploded"
    assert (
        generation_trace.kwargs["extra"]["prompt_entries"][0]["was_truncated"] is True
    )
    assert "generated_response_preview" in generation_trace.kwargs["extra"]
    assert generation_trace.kwargs["extra"]["fallback_reason"] == "generation_exception"
    assert (
        generation_trace.kwargs["extra"]["semantic_grounding_status"]
        == "not_applicable"
    )
    assert result["technical_failure_stage"] == "response_generator"
