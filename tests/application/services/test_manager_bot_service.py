import json
from unittest.mock import AsyncMock

import pytest

from src.domain.project_plane.manager_assignments import ManagerActor
from src.application.services.manager_bot_service import ManagerBotService


@pytest.mark.asyncio
async def test_claim_thread_starts_reply_session():
    orchestrator = AsyncMock()
    orchestrator.resolve_manager_user_id_by_telegram = AsyncMock(return_value="user-1")
    orchestrator.claim_thread_for_manager = AsyncMock()
    redis = AsyncMock()
    telegram_client = AsyncMock()
    service = ManagerBotService(
        orchestrator,
        redis,
        "bot-token",
        "project-1",
        telegram_client=telegram_client,
    )

    result = await service.claim_thread(
        callback_id="callback-1",
        thread_id="thread-1",
        manager_chat_id="12345",
    )

    assert result.to_dict() == {"ok": True}
    redis.setex.assert_any_await(
        "awaiting_reply_thread:thread-1",
        600,
        json.dumps({"manager_chat_id": "12345", "manager_user_id": "user-1"}),
    )
    redis.setex.assert_any_await("awaiting_reply:12345", 600, "thread-1")
    orchestrator.resolve_manager_user_id_by_telegram.assert_awaited_once_with(
        "project-1", "12345"
    )
    orchestrator.claim_thread_for_manager.assert_awaited_once_with(
        "thread-1",
        manager=ManagerActor(user_id="user-1", telegram_chat_id="12345"),
    )
    assert telegram_client.post_json.await_count == 2


@pytest.mark.asyncio
async def test_reply_from_manager_without_active_session_sends_hint():
    orchestrator = AsyncMock()
    orchestrator.resolve_manager_user_id_by_telegram = AsyncMock(return_value="user-1")
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    telegram_client = AsyncMock()
    service = ManagerBotService(
        orchestrator,
        redis,
        "bot-token",
        "project-1",
        telegram_client=telegram_client,
    )

    result = await service.reply_from_manager(manager_chat_id="12345", text="hello")

    assert result.to_dict() == {"ok": True}
    orchestrator.resolve_manager_user_id_by_telegram.assert_awaited_once_with(
        "project-1", "12345"
    )
    orchestrator.manager_reply.assert_not_called()
    telegram_client.post_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_thread_uses_orchestrator_boundary_method():
    orchestrator = AsyncMock()
    orchestrator.resolve_manager_user_id_by_telegram = AsyncMock(return_value="user-1")
    orchestrator.close_thread_for_manager = AsyncMock()
    redis = AsyncMock()
    telegram_client = AsyncMock()
    service = ManagerBotService(
        orchestrator,
        redis,
        "bot-token",
        "project-1",
        telegram_client=telegram_client,
    )

    result = await service.close_thread(
        callback_id="callback-1",
        thread_id="thread-1",
        manager_chat_id="12345",
    )

    assert result.to_dict() == {"ok": True}
    orchestrator.resolve_manager_user_id_by_telegram.assert_awaited_once_with(
        "project-1", "12345"
    )
    redis.delete.assert_any_await("awaiting_reply_thread:thread-1")
    redis.delete.assert_any_await("awaiting_reply:12345")
    orchestrator.close_thread_for_manager.assert_awaited_once_with("thread-1")
    telegram_client.post_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_thread_denies_unknown_manager_without_mutating_state():
    orchestrator = AsyncMock()
    orchestrator.resolve_manager_user_id_by_telegram = AsyncMock(return_value=None)
    orchestrator.claim_thread_for_manager = AsyncMock()
    redis = AsyncMock()
    telegram_client = AsyncMock()
    service = ManagerBotService(
        orchestrator,
        redis,
        "bot-token",
        "project-1",
        telegram_client=telegram_client,
    )

    result = await service.claim_thread(
        callback_id="callback-1",
        thread_id="thread-1",
        manager_chat_id="12345",
    )

    assert result.to_dict() == {"ok": True}
    redis.setex.assert_not_called()
    orchestrator.claim_thread_for_manager.assert_not_called()
    telegram_client.post_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_reply_from_manager_denies_unknown_manager_without_replying():
    orchestrator = AsyncMock()
    orchestrator.resolve_manager_user_id_by_telegram = AsyncMock(return_value=None)
    orchestrator.manager_reply = AsyncMock()
    redis = AsyncMock()
    telegram_client = AsyncMock()
    service = ManagerBotService(
        orchestrator,
        redis,
        "bot-token",
        "project-1",
        telegram_client=telegram_client,
    )

    result = await service.reply_from_manager(manager_chat_id="12345", text="hello")

    assert result.to_dict() == {"ok": True}
    redis.get.assert_not_called()
    orchestrator.manager_reply.assert_not_called()
    telegram_client.post_json.assert_awaited_once()
