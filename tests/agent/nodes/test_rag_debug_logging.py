from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.kb_search import create_kb_search_node
from src.agent.nodes.response_generator import create_response_generator_node


async def _passthrough(_name, impl, state, **_kwargs):
    return await impl(state)


@pytest.mark.asyncio
async def test_rag_debug_true_emits_retrieval_and_generation_traces(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "true")

    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value={
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
    kb_node = create_kb_search_node(tool_registry)

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="Axole помогает."))
    response_node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Что умеет сервис?",
        "decision": "LLM_GENERATE",
        "project_configuration": {"settings": {"target_language": "ru"}},
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

    ordinary_logs = [
        call.args[0] for call in kb_logger.info.call_args_list if call.args
    ]
    assert "KB search start" in ordinary_logs
    assert "KB search result" in ordinary_logs


@pytest.mark.asyncio
async def test_rag_debug_false_suppresses_extended_traces(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "false")

    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(return_value={"results": []})
    kb_node = create_kb_search_node(tool_registry)

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="Axole помогает."))
    response_node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    state = {
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "Что умеет сервис?",
        "decision": "LLM_GENERATE",
        "project_configuration": {"settings": {"target_language": "ru"}},
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
