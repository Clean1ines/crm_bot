from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.persist import create_persist_node


@pytest.mark.asyncio
async def test_persist_returns_error_when_required_ids_missing():
    node = create_persist_node(thread_repo=MagicMock())

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.persist.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({"response_text": "ok"})

    assert result == {"error": "Missing thread_id or project_id"}


@pytest.mark.asyncio
async def test_persist_saves_state_emits_events_and_updates_analytics():
    thread_repo = MagicMock()
    thread_repo.add_message = AsyncMock()
    thread_repo.save_state_json = AsyncMock()
    thread_repo.update_analytics = AsyncMock()
    thread_repo.get_message_counts_view = AsyncMock(
        return_value=SimpleNamespace(total=3, ai=2, manager=1)
    )
    thread_repo.get_thread_with_project_view = AsyncMock(
        return_value=SimpleNamespace(created_at=datetime.now(UTC))
    )

    event_repo = MagicMock()
    event_repo.append = AsyncMock()

    memory_repo = MagicMock()
    memory_repo.set = AsyncMock()

    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()

    node = create_persist_node(
        thread_repo=thread_repo,
        event_repo=event_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    state = {
        "thread_id": "thread-1",
        "project_id": "project-1",
        "client_id": "client-1",
        "response_text": "hello",
        "user_input": "не хочу звонок, слишком дорого",
        "intent": "ask_price",
        "lifecycle": "warm",
        "cta": "call_manager",
        "decision": "ESCALATE_TO_HUMAN",
        "requires_human": True,
        "close_ticket": True,
        "state_payload": {},
    }

    with patch("src.agent.nodes.persist.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node(state)

    assert result == {}
    thread_repo.add_message.assert_awaited_once()
    thread_repo.save_state_json.assert_awaited_once()
    thread_repo.update_analytics.assert_awaited_once()
    thread_repo.get_message_counts_view.assert_awaited_once_with("thread-1")
    thread_repo.get_thread_with_project_view.assert_awaited_once_with("thread-1")
    assert event_repo.append.await_count >= 2
    assert memory_repo.set.await_count >= 3
    queue_repo.enqueue.assert_awaited_once()
