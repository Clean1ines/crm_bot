from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.kb_search import create_kb_search_node
from src.domain.runtime.knowledge_search import KnowledgeSearchResult
from src.domain.runtime.tool_execution import ToolExecutionOutcome


@pytest.mark.asyncio
async def test_kb_search_returns_empty_chunks_when_context_missing():
    node = create_kb_search_node(tool_registry=MagicMock())

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.kb_search.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({})

    assert result == {
        "knowledge_chunks": [],
        "knowledge_retrieval_status": "skipped",
        "knowledge_retrieval_error_type": None,
    }


@pytest.mark.asyncio
async def test_kb_search_normalizes_tool_results():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(
            payload={
                "results": [
                    {"id": "chunk-1", "score": 0.9, "content": "abc"},
                    {"score": None, "content": "xyz"},
                ]
            }
        )
    )
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.kb_search.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"project_id": "project-1", "user_input": "hello"})

    assert result == {
        "knowledge_chunks": [
            {"id": "chunk-1", "score": 0.9, "content": "abc"},
            {"id": "no-id-1", "score": None, "content": "xyz"},
        ],
        "knowledge_retrieval_status": "retrieved",
        "knowledge_retrieval_error_type": None,
    }
    tool_registry.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_kb_search_keeps_full_curated_claim_text():
    claim = (
        "Workbench runtime facts must stay complete until prompt formatting owns "
        "the final prompt budget, because the last clause can carry the exact "
        "customer-facing limitation that prevents a misleading answer."
    )
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(
            payload={
                "results": [{"id": "runtime-entry-1", "score": 0.93, "content": claim}]
            }
        )
    )
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.kb_search.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"project_id": "project-1", "user_input": "hello"})

    assert result == {
        "knowledge_chunks": [
            {"id": "runtime-entry-1", "score": 0.93, "content": claim}
        ],
        "knowledge_retrieval_status": "retrieved",
        "knowledge_retrieval_error_type": None,
    }


@pytest.mark.asyncio
async def test_kb_search_uses_resolved_knowledge_query_for_short_continuation_reply():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.kb_search.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        await node(
            {
                "project_id": "project-1",
                "thread_id": "thread-1",
                "user_input": "Да",
                "knowledge_query": "подробнее как это работает возможности продукта",
                "knowledge_query_source": "canonical_continue_explanation",
                "turn_relation": "continuation",
                "topic": "product",
                "cta": "continue_explanation",
                "should_search_kb": True,
            }
        )

    called_args = tool_registry.execute.await_args.args[1]
    assert called_args["query"] != "Да"
    assert "продукт" in called_args["query"]


@pytest.mark.asyncio
async def test_kb_search_ignores_stale_knowledge_query_on_independent_turn():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.kb_search.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        await node(
            {
                "project_id": "project-1",
                "thread_id": "thread-1",
                "user_input": "Сколько это стоит?",
                "knowledge_query": "подробнее как работает продукт и его возможности",
                "knowledge_query_source": "model_contextual",
                "turn_relation": "new_topic",
                "topic": "pricing",
                "cta": "none",
                "should_search_kb": True,
            }
        )

    called_args = tool_registry.execute.await_args.args[1]
    assert called_args["query"] == "Сколько это стоит?"


@pytest.mark.asyncio
async def test_kb_search_logs_literal_query_trace_payload():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.kb_search.logger") as kb_logger,
    ):
        await node(
            {
                "project_id": "project-1",
                "thread_id": "thread-1",
                "user_input": "Что умеет продукт?",
                "knowledge_query": "старая подсказка",
                "knowledge_query_source": "model_contextual",
                "turn_relation": "new_topic",
                "topic": "product",
                "cta": "none",
                "resolved_cta": "none",
                "resolved_cta_reply": None,
                "should_search_kb": True,
            }
        )

    start = [
        call
        for call in kb_logger.info.call_args_list
        if call.args and call.args[0] == "KB search start"
    ][-1]
    extra = start.kwargs["extra"]
    assert extra["query_source"] == "none"
    assert extra["resolved_query_used"] is False
    assert extra["original_user_input_preview"] == "Что умеет продукт?"
    assert extra["resolved_query_preview"] is None
    assert extra["resolved_query_hash"] is None
    assert extra["resolved_query_len"] == 0
    assert extra["turn_relation"] == "new_topic"
    assert extra["topic"] == "product"
    assert extra["cta"] == "none"
    assert extra["resolved_cta"] == "none"
    assert extra["resolved_cta_reply"] is None


@pytest.mark.asyncio
async def test_kb_search_logs_model_contextual_query_trace_payload(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "true")
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.kb_search.logger") as kb_logger,
    ):
        await node(
            {
                "project_id": "project-1",
                "thread_id": "thread-1",
                "user_input": "А роли?",
                "knowledge_query": "какие роли есть в проекте",
                "knowledge_query_source": "model_contextual",
                "turn_relation": "continuation",
                "topic": "product",
                "cta": "none",
                "resolved_cta": "none",
                "resolved_cta_reply": None,
                "should_search_kb": True,
            }
        )

    trace = [
        call
        for call in kb_logger.info.call_args_list
        if call.args and call.args[0] == "RAG semantic retrieval trace"
    ][-1]
    extra = trace.kwargs["extra"]
    assert extra["query_source"] == "model_contextual"
    assert extra["resolved_query_used"] is True
    assert extra["original_user_input_preview"] == "А роли?"
    assert extra["resolved_query_preview"] == "какие роли есть в проекте"
    assert extra["resolved_query_hash"]
    assert extra["resolved_query_len"] == len("какие роли есть в проекте")


@pytest.mark.asyncio
async def test_kb_search_logs_rejected_contextual_query_trace_payload(monkeypatch):
    monkeypatch.setenv("RAG_DEBUG", "true")
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"results": []})
    )
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.kb_search.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.kb_search.logger") as kb_logger,
    ):
        await node(
            {
                "project_id": "project-1",
                "thread_id": "thread-1",
                "user_input": "нет",
                "knowledge_query": "какие роли есть в проекте",
                "knowledge_query_source": "model_contextual",
                "turn_relation": "continuation",
                "topic": "product",
                "cta": "continue_explanation",
                "resolved_cta": "continue_explanation",
                "resolved_cta_reply": "negative",
                "should_search_kb": True,
            }
        )

    trace = [
        call
        for call in kb_logger.info.call_args_list
        if call.args and call.args[0] == "RAG semantic retrieval trace"
    ][-1]
    extra = trace.kwargs["extra"]
    assert extra["query_source"] == "none"
    assert extra["resolved_query_used"] is False
    assert extra["resolved_query_preview"] is None
    assert extra["resolved_query_len"] == 0


def test_knowledge_search_result_keeps_trace_metadata_outside_prompt_payload():
    result = KnowledgeSearchResult.from_tool_payload(
        {
            "results": [
                {
                    "id": "runtime-entry-1",
                    "score": 0.91,
                    "content": "Axole helps businesses automate client replies.",
                    "method": "hybrid",
                    "source": "company.md",
                    "title": "Axole for business",
                    "entry_kind": "faq_workbench_fact",
                    "document_id": "source-document-1",
                    "source_excerpt": "Axole automates support in Telegram.",
                    "questions": ["How can Axole help my business?"],
                }
            ]
        }
    )

    chunk = result.chunks[0]
    assert chunk.method == "hybrid"
    assert chunk.source == "company.md"
    assert chunk.title == "Axole for business"
    assert chunk.entry_kind == "faq_workbench_fact"
    assert chunk.document_id == "source-document-1"
    assert chunk.source_excerpt == "Axole automates support in Telegram."
    assert chunk.questions == ["How can Axole help my business?"]
    assert chunk.to_prompt_payload() == {
        "id": "runtime-entry-1",
        "score": 0.91,
        "content": "Axole helps businesses automate client replies.",
    }
    assert result.to_state_patch() == {
        "knowledge_chunks": [
            {
                "id": "runtime-entry-1",
                "score": 0.91,
                "content": "Axole helps businesses automate client replies.",
            }
        ],
        "knowledge_retrieval_status": "retrieved",
        "knowledge_retrieval_error_type": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (TimeoutError("slow search"), "tool_timeout"),
        (ConnectionError("provider unavailable"), "tool_unavailable"),
        (RuntimeError("search unavailable"), "knowledge_search_failed"),
    ],
)
async def test_kb_search_marks_retrieval_exception_with_stable_code(
    exception, expected_code
):
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(side_effect=exception)
    node = create_kb_search_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.kb_search.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"project_id": "project-1", "user_input": "hello"})

    assert result == {
        "knowledge_chunks": [],
        "knowledge_retrieval_status": "failed",
        "knowledge_retrieval_error_type": expected_code,
    }
    assert type(exception).__name__ not in result.values()
