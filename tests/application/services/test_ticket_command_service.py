import json
from unittest.mock import AsyncMock

import pytest

from src.application.services.ticket_command_service import (
    MANAGER_CLAIM_IDLE_TIMEOUT_SECONDS,
    TicketCommandService,
)
from src.domain.project_plane.manager_assignments import ManagerActor


@pytest.mark.asyncio
async def test_claim_ticket_starts_platform_manager_session() -> None:
    orchestrator = AsyncMock()
    cache = AsyncMock()
    service = TicketCommandService(orchestrator, cache)

    result = await service.claim_ticket(thread_id="thread-1", manager_user_id="user-1")

    assert result == {"status": "claimed"}
    orchestrator.claim_thread_for_manager.assert_awaited_once_with(
        "thread-1",
        manager=ManagerActor(user_id="user-1"),
    )
    cache.set.assert_awaited_once_with(
        "awaiting_reply_thread:thread-1",
        json.dumps(
            {
                "manager_chat_id": None,
                "manager_user_id": "user-1",
                "has_manager_reply": False,
                "claimed_at_unix": None,
            }
        ),
    )


@pytest.mark.asyncio
async def test_close_ticket_clears_platform_manager_session() -> None:
    orchestrator = AsyncMock()
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    service = TicketCommandService(orchestrator, cache)

    result = await service.close_ticket(thread_id="thread-1")

    assert result == {"status": "closed"}
    cache.delete.assert_awaited_once_with("awaiting_reply_thread:thread-1")
    orchestrator.close_thread_for_manager.assert_awaited_once_with("thread-1")


@pytest.mark.asyncio
async def test_mark_ticket_replied_refreshes_web_session_timeout() -> None:
    orchestrator = AsyncMock()
    cache = AsyncMock()
    service = TicketCommandService(orchestrator, cache)

    await service.mark_ticket_replied(thread_id="thread-1", manager_user_id="user-1")

    cache.setex.assert_awaited_once_with(
        "awaiting_reply_thread:thread-1",
        MANAGER_CLAIM_IDLE_TIMEOUT_SECONDS,
        json.dumps(
            {
                "manager_chat_id": None,
                "manager_user_id": "user-1",
                "has_manager_reply": True,
                "claimed_at_unix": None,
            }
        ),
    )


@pytest.mark.asyncio
async def test_close_ticket_clears_telegram_manager_bridge_when_present() -> None:
    orchestrator = AsyncMock()
    cache = AsyncMock()
    cache.get = AsyncMock(
        return_value=json.dumps(
            {
                "manager_chat_id": "12345",
                "manager_user_id": "user-1",
                "has_manager_reply": True,
                "claimed_at_unix": None,
            }
        )
    )
    service = TicketCommandService(orchestrator, cache)

    await service.close_ticket(thread_id="thread-1")

    cache.delete.assert_any_await("awaiting_reply:12345")
    cache.delete.assert_any_await("awaiting_reply_thread:thread-1")
