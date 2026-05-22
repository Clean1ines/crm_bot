from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.commercial_context_lookup import (
    create_commercial_context_lookup_node,
)


@pytest.mark.asyncio
async def test_commercial_context_lookup_skips_when_context_missing() -> None:
    node = create_commercial_context_lookup_node(tool_registry=MagicMock())

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.commercial_context_lookup.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({})

    assert result == {
        "commercial_context": {
            "decision": "skipped",
            "reason": "missing_project_or_query",
        },
        "commercial_context_status": "skipped",
        "commercial_context_sources": [],
    }


@pytest.mark.asyncio
async def test_commercial_context_lookup_stores_tool_payload() -> None:
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value={
            "decision": "answerable",
            "facts": [
                {
                    "id": "fact-1",
                    "source_refs": [
                        {
                            "price_document_id": "price-doc-1",
                            "source_unit_id": "unit-1",
                            "quote": "Pro — 2490 ₽/мес.",
                        }
                    ],
                }
            ],
        }
    )
    node = create_commercial_context_lookup_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.commercial_context_lookup.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "project_id": "project-1",
                "thread_id": "thread-1",
                "user_input": "Сколько стоит Pro?",
            }
        )

    assert result["commercial_context_status"] == "answerable"
    assert result["commercial_context"] == {
        "decision": "answerable",
        "facts": [
            {
                "id": "fact-1",
                "source_refs": [
                    {
                        "price_document_id": "price-doc-1",
                        "source_unit_id": "unit-1",
                        "quote": "Pro — 2490 ₽/мес.",
                    }
                ],
            }
        ],
    }
    assert result["commercial_context_sources"] == [
        {
            "price_document_id": "price-doc-1",
            "source_unit_id": "unit-1",
            "quote": "Pro — 2490 ₽/мес.",
        }
    ]
    tool_registry.execute.assert_awaited_once_with(
        "commercial_price_lookup",
        {"item_name": "Сколько стоит Pro?", "limit": 5},
        context={"project_id": "project-1", "thread_id": "thread-1"},
    )


@pytest.mark.asyncio
async def test_commercial_context_lookup_degrades_to_kb_search_on_error() -> None:
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(side_effect=RuntimeError("boom"))
    node = create_commercial_context_lookup_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.commercial_context_lookup.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"project_id": "project-1", "user_input": "price"})

    assert result == {
        "commercial_context": {
            "decision": "error",
            "reason": "tool_execution_failed",
        },
        "commercial_context_status": "error",
        "commercial_context_sources": [],
    }
