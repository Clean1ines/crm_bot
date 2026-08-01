from unittest.mock import AsyncMock, patch

import pytest

from src.interfaces.telegram.client_bot import process_client_update


@pytest.mark.asyncio
async def test_process_client_update_passes_profile_to_orchestrator():
    orchestrator = AsyncMock()
    orchestrator.process_message = AsyncMock(return_value="")
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    redis.setex = AsyncMock()

    update = {
        "update_id": 1,
        "message": {
            "chat": {"id": 12345},
            "from": {
                "id": 12345,
                "username": "client_username",
                "first_name": "Client",
                "last_name": "Name",
            },
            "text": "hello",
        },
    }

    with patch(
        "src.interfaces.telegram.client_bot.get_redis_client",
        AsyncMock(return_value=redis),
    ):
        result = await process_client_update(
            update, "project-1", orchestrator, "bot-token"
        )

    assert result == {"ok": True}
    orchestrator.process_message.assert_awaited_once_with(
        project_id="project-1",
        chat_id=12345,
        text="hello",
        username="client_username",
        full_name="Client Name",
        source="telegram",
    )


@pytest.mark.asyncio
async def test_reset_dialog_command_does_not_call_regular_message_processing():
    orchestrator = AsyncMock()
    orchestrator.process_message = AsyncMock(return_value="regular")
    orchestrator.reset_dialog_by_telegram_admin = AsyncMock(return_value="reset")
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    redis.setex = AsyncMock()

    update = {
        "update_id": 2,
        "message": {
            "chat": {"id": 12345},
            "from": {"id": 999, "username": "admin", "first_name": "Admin"},
            "text": "/reset_dialog",
        },
    }

    with (
        patch(
            "src.interfaces.telegram.client_bot.get_redis_client",
            AsyncMock(return_value=redis),
        ),
        patch(
            "src.interfaces.telegram.client_bot._send_telegram_message", AsyncMock()
        ) as send_message,
    ):
        result = await process_client_update(
            update, "project-1", orchestrator, "bot-token"
        )

    assert result == {"ok": True}
    orchestrator.process_message.assert_not_awaited()
    orchestrator.reset_dialog_by_telegram_admin.assert_awaited_once()
    send_message.assert_awaited_once_with("bot-token", 12345, "reset")
