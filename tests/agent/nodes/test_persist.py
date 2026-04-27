from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.nodes.persist import create_persist_node
from src.domain.project_plane.thread_views import (
    ThreadMessageCounts,
    ThreadWithProjectView,
)


@pytest.mark.asyncio
async def test_persist_node_requires_thread_and_project_ids():
    node = create_persist_node(
        thread_message_repo=MagicMock(),
        thread_runtime_state_repo=MagicMock(),
        thread_read_repo=MagicMock(),
    )

    result = await node({})

    assert result == {"error": "Missing thread_id or project_id"}


@pytest.mark.asyncio
async def test_persist_saves_state_emits_events_and_updates_analytics():
    thread_message_repo = MagicMock()
    thread_message_repo.add_message = AsyncMock()
    thread_message_repo.get_message_counts_view = AsyncMock(
        return_value=ThreadMessageCounts(total=3, ai=2, manager=1)
    )

    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.save_state_json = AsyncMock()
    thread_runtime_state_repo.update_analytics = AsyncMock()

    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value=ThreadWithProjectView.from_record(
            {
                "id": "thread-1",
                "client_id": "client-1",
                "status": "active",
                "manager_user_id": None,
                "manager_chat_id": None,
                "context_summary": None,
                "created_at": None,
                "updated_at": None,
                "project_id": "project-1",
                "full_name": None,
                "username": None,
                "chat_id": None,
            }
        )
    )

    event_repo = MagicMock()
    event_repo.append = AsyncMock()

    memory_repo = MagicMock()
    memory_repo.set = AsyncMock()

    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()

    node = create_persist_node(
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        thread_read_repo=thread_read_repo,
        event_repo=event_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
    )

    result = await node(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "response_text": "hello",
            "confidence": 0.9,
            "requires_human": True,
            "intent": "pricing",
            "lifecycle": "warm",
            "cta": "call_manager",
            "decision": "ESCALATE",
            "dialog_state": {"lifecycle": "warm"},
        }
    )

    assert result == {}

    thread_message_repo.add_message.assert_awaited_once()
    thread_runtime_state_repo.save_state_json.assert_awaited_once()
    thread_runtime_state_repo.update_analytics.assert_awaited_once()
    thread_message_repo.get_message_counts_view.assert_not_awaited()
    thread_read_repo.get_thread_with_project_view.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_degrades_when_assistant_message_save_fails():
    thread_message_repo = MagicMock()
    thread_message_repo.add_message = AsyncMock(
        side_effect=RuntimeError("message write failed")
    )
    thread_message_repo.get_message_counts_view = AsyncMock(
        return_value=ThreadMessageCounts(total=0, ai=0, manager=0)
    )

    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.save_state_json = AsyncMock()
    thread_runtime_state_repo.update_analytics = AsyncMock()

    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(return_value=None)

    node = create_persist_node(
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        thread_read_repo=thread_read_repo,
    )

    result = await node(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "response_text": "hello",
            "intent": "support",
        }
    )

    assert result == {}
    thread_runtime_state_repo.save_state_json.assert_awaited_once()
    thread_runtime_state_repo.update_analytics.assert_awaited_once()
