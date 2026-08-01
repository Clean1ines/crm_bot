from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.orchestration.manager_reply_service import ManagerReplyService
from src.domain.project_plane.manager_assignments import ManagerActor


@pytest.mark.asyncio
async def test_claim_thread_for_manager_rejects_missing_thread_after_claim() -> None:
    lifecycle = AsyncMock()
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=None)

    service = ManagerReplyService(
        projects=MagicMock(),
        threads=lifecycle,
        thread_messages=AsyncMock(),
        thread_read=read,
        thread_runtime_state=AsyncMock(),
        memory_repo=AsyncMock(),
        telegram_client=AsyncMock(),
        event_emitter=AsyncMock(),
        logger=MagicMock(),
    )

    with pytest.raises(ValueError, match="Thread thread-1 not found"):
        await service.claim_thread_for_manager(
            "thread-1",
            manager=ManagerActor(user_id="manager-1", telegram_chat_id="12345"),
        )

    lifecycle.claim_for_manager.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_thread_for_manager_delegates_ticket_resolution_generation() -> (
    None
):
    lifecycle = AsyncMock()
    lifecycle.close_manager_ticket = AsyncMock()
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=None)
    ticket_resolution_service = AsyncMock()
    ticket_resolution_service.generate_after_manager_close = AsyncMock()

    service = ManagerReplyService(
        projects=MagicMock(),
        threads=lifecycle,
        thread_messages=AsyncMock(),
        thread_read=read,
        thread_runtime_state=AsyncMock(),
        memory_repo=AsyncMock(),
        ticket_resolution_service=ticket_resolution_service,
        telegram_client=AsyncMock(),
        event_emitter=AsyncMock(),
        logger=MagicMock(),
    )

    await service.close_thread_for_manager("thread-1")

    lifecycle.close_manager_ticket.assert_awaited_once_with("thread-1")
    ticket_resolution_service.generate_after_manager_close.assert_awaited_once_with(
        "thread-1"
    )
