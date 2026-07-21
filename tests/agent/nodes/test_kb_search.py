from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.kb_search import create_kb_search_node
from src.domain.runtime.knowledge_search import KnowledgeSearchResult


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

    assert result == {"knowledge_chunks": []}


@pytest.mark.asyncio
async def test_kb_search_normalizes_tool_results():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value={
            "results": [
                {"id": "chunk-1", "score": 0.9, "content": "abc"},
                {"score": None, "content": "xyz"},
            ]
        }
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
        ]
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
        return_value={
            "results": [{"id": "runtime-entry-1", "score": 0.93, "content": claim}]
        }
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
        "knowledge_chunks": [{"id": "runtime-entry-1", "score": 0.93, "content": claim}]
    }


@pytest.mark.asyncio
async def test_kb_search_uses_resolved_knowledge_query_for_short_continuation_reply():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(return_value={"results": []})
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
                "turn_relation": "continuation",
                "topic": "product",
                "cta": "continue_explanation",
            }
        )

    called_args = tool_registry.execute.await_args.args[1]
    assert called_args["query"] != "Да"
    assert "продукт" in called_args["query"]


@pytest.mark.asyncio
async def test_kb_search_ignores_stale_knowledge_query_on_independent_turn():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(return_value={"results": []})
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
                "turn_relation": "new_topic",
                "topic": "pricing",
                "cta": "none",
            }
        )

    called_args = tool_registry.execute.await_args.args[1]
    assert called_args["query"] == "Сколько это стоит?"


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
        ]
    }
