from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
)


def make_orchestrator():
    return ConversationOrchestrator(
        db_conn=MagicMock(),
        project_repo=MagicMock(),
        thread_lifecycle_repo=MagicMock(),
        thread_message_repo=MagicMock(),
        thread_runtime_state_repo=MagicMock(),
        thread_read_repo=MagicMock(),
        queue_repo=MagicMock(),
        event_repo=MagicMock(),
        tool_registry=MagicMock(),
        memory_repo=MagicMock(),
        logger=MagicMock(),
        agent_factory=MagicMock(return_value=MagicMock()),
    )


@pytest.mark.asyncio
async def test_process_message_delegates_to_client_message_service():
    orchestrator = make_orchestrator()
    orchestrator.client_messages.process_message = AsyncMock(return_value="ok")

    result = await orchestrator.process_message(
        project_id="project-id",
        chat_id=123,
        text="hello",
        username="u",
        full_name="User",
    )

    assert result == "ok"
    orchestrator.client_messages.process_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_manager_reply_delegates_to_manager_reply_service():
    orchestrator = make_orchestrator()
    orchestrator.manager_replies.manager_reply = AsyncMock(return_value=True)

    result = await orchestrator.manager_reply(
        thread_id="thread-id",
        manager_text="reply",
        manager_chat_id="123",
        manager_user_id="user-id",
    )

    assert result is True
    orchestrator.manager_replies.manager_reply.assert_awaited_once()
