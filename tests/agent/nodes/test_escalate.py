from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.escalate import create_escalate_node


@pytest.mark.asyncio
async def test_escalate_returns_fallback_when_thread_id_missing():
    node = create_escalate_node(
        thread_repo=MagicMock(),
        queue_repo=MagicMock(),
        ticket_create_tool=MagicMock(),
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.escalate.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({"project_id": "project-1"})

    assert result["requires_human"] is True
    assert result["tool_result"] is None


@pytest.mark.asyncio
async def test_escalate_creates_ticket_and_enqueues_notifications():
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(return_value={"ticket_id": "ticket-1"})
    node = create_escalate_node(
        thread_repo=MagicMock(),
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.escalate.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": "need help",
                "client_profile": {"id": "client-1"},
            }
        )

    assert result["requires_human"] is True
    assert queue_repo.enqueue.await_count == 2
    ticket_create_tool.run.assert_awaited_once()
