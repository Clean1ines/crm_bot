from unittest.mock import AsyncMock

import pytest

from src.application.errors import ValidationError
from src.application.services.project_command_service import ProjectCommandService


class _Repo:
    def __init__(self) -> None:
        self.project_exists = AsyncMock(return_value=True)
        self.set_bot_token = AsyncMock()
        self.set_manager_bot_token = AsyncMock()
        self.get_bot_token = AsyncMock(return_value="old-client-token")
        self.get_manager_bot_token = AsyncMock(return_value="old-manager-token")
        self.upsert_project_channel = AsyncMock()


class _Access:
    def __init__(self) -> None:
        self.require_project_role = AsyncMock()


class _Query:
    pass


class _Telegram:
    def __init__(self) -> None:
        self.post_json = AsyncMock(return_value={"ok": True})


def _service(repo: _Repo, telegram: _Telegram) -> ProjectCommandService:
    return ProjectCommandService(
        repo,
        _Access(),
        _Query(),
        telegram_client=telegram,
    )


@pytest.mark.asyncio
async def test_rejects_platform_admin_token_as_client_bot(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.application.services.project_command_service.settings.ADMIN_BOT_TOKEN",
        "admin-token",
    )
    repo = _Repo()

    with pytest.raises(ValidationError) as exc:
        await _service(repo, _Telegram()).set_client_bot_token(
            "project-1",
            "user-1",
            "admin-token",
        )

    assert "Platform admin bot token cannot be used as client bot token" in str(
        exc.value
    )
    repo.set_bot_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_client_bot_token_deletes_existing_telegram_webhook() -> None:
    repo = _Repo()
    telegram = _Telegram()

    result = await _service(repo, telegram).clear_client_bot_token(
        "project-1",
        "user-1",
    )

    telegram.post_json.assert_awaited_once_with(
        "old-client-token",
        "deleteWebhook",
        {"drop_pending_updates": True},
    )
    repo.set_bot_token.assert_awaited_once_with("project-1", None)
    assert result.to_dict() == {"status": "ok", "type": "client"}


@pytest.mark.asyncio
async def test_clear_client_bot_token_continues_when_webhook_cleanup_fails() -> None:
    repo = _Repo()
    telegram = _Telegram()
    telegram.post_json.side_effect = RuntimeError("telegram unavailable")

    result = await _service(repo, telegram).clear_client_bot_token(
        "project-1",
        "user-1",
    )

    repo.set_bot_token.assert_awaited_once_with("project-1", None)
    assert result.to_dict() == {"status": "ok", "type": "client"}
