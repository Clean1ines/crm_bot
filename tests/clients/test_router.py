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
