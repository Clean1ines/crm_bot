from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.load_state import create_load_state_node
from src.domain.project_plane.memory_views import MemoryEntryView


@pytest.mark.asyncio
async def test_load_state_node_uses_thread_runtime_snapshots():
    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
            "context_summary": "summary",
            "chat_id": 123,
        }
    )
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.get_analytics_view = AsyncMock(
        return_value=SimpleNamespace(
            to_record=lambda: {
                "intent": "pricing",
                "lifecycle": "warm",
                "cta": None,
                "decision": "RESPOND",
            }
        )
    )
    thread_message_repo = MagicMock()
    thread_message_repo.get_messages_for_langgraph = AsyncMock(
        return_value=[{"role": "user", "content": "hello"}]
    )
    thread_runtime_state_repo.get_state_json = AsyncMock(return_value={"ignored": True})

    node = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        project_repo=MagicMock(),
        memory_repo=None,
    )

    result = await node({"thread_id": "thread-1", "project_id": "project-1"})

    assert result["conversation_summary"] == "summary"
    assert result["client_id"] == "client-1"
    assert result["history"] == [{"role": "user", "content": "hello"}]
    assert result["intent"] == "pricing"
    assert result["lifecycle"] == "warm"
    assert result["decision"] == "RESPOND"
    assert result["user_memory"] == {}


@pytest.mark.asyncio
async def test_load_state_degrades_to_empty_user_memory_when_memory_repo_fails():
    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
            "context_summary": "summary",
            "chat_id": 123,
        }
    )
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.get_analytics_view = AsyncMock(return_value=None)
    thread_runtime_state_repo.get_state_json = AsyncMock(return_value={})

    thread_message_repo = MagicMock()
    thread_message_repo.get_messages_for_langgraph = AsyncMock(return_value=[])

    memory_repo = MagicMock()
    memory_repo.get_for_user_view = AsyncMock(
        side_effect=RuntimeError("memory unavailable")
    )

    node = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        project_repo=MagicMock(),
        memory_repo=memory_repo,
    )

    with patch("src.agent.nodes.load_state.logger") as logger:
        result = await node({"thread_id": "thread-1", "project_id": "project-1"})

    assert result["user_memory"] == {}
    logger.exception.assert_called_once()
    assert (
        logger.exception.call_args.kwargs["extra"]["policy"] == "fallback_empty_memory"
    )


@pytest.mark.asyncio
async def test_load_state_indexes_memory_and_hydrates_dialog_state():
    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
            "context_summary": "summary",
        }
    )
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.get_analytics_view = AsyncMock(return_value=None)
    thread_runtime_state_repo.get_state_json = AsyncMock(return_value={})

    thread_message_repo = MagicMock()
    thread_message_repo.get_messages_for_langgraph = AsyncMock(return_value=[])

    memory_repo = MagicMock()
    memory_repo.get_for_user_view = AsyncMock(
        return_value=[
            MemoryEntryView(
                id="memory-1",
                key="dialog_state",
                value={"repeat_count": 2, "last_topic": "pricing"},
                type="dialog_state",
            ),
            MemoryEntryView(
                id="memory-2",
                key="contact_preference",
                value={"preferred_channel": "chat", "avoid_calls": True},
                type="preferences",
            ),
        ]
    )

    node = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        project_repo=MagicMock(),
        memory_repo=memory_repo,
    )

    result = await node({"thread_id": "thread-1", "project_id": "project-1"})

    assert result["user_memory"] == {
        "dialog_state": [
            {
                "key": "dialog_state",
                "value": {"repeat_count": 2, "last_topic": "pricing"},
            }
        ],
        "preferences": [
            {
                "key": "contact_preference",
                "value": {"preferred_channel": "chat", "avoid_calls": True},
            }
        ],
    }
    assert result["dialog_state"]["repeat_count"] == 2
    assert result["dialog_state"]["last_topic"] == "pricing"
