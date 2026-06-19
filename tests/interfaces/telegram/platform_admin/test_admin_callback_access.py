from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.interfaces.telegram.platform_admin import handlers


@dataclass(slots=True)
class _FakePlatformBotService:
    project_ids: tuple[str, ...]

    async def list_projects_for_telegram_user(self, telegram_chat_id: int):
        assert telegram_chat_id == 123
        return SimpleNamespace(
            projects=tuple(
                SimpleNamespace(id=project_id) for project_id in self.project_ids
            )
        )


@pytest.mark.asyncio
async def test_help_token_button_has_a_callback_handler() -> None:
    text, keyboard = await handlers.handle_admin_callback(
        "help_token",
        "123",
        pool=object(),
    )

    assert "@BotFather" in text
    assert keyboard is not None


@pytest.mark.asyncio
async def test_cross_project_callback_is_rejected_before_project_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handlers,
        "_build_platform_bot_service",
        lambda pool: _FakePlatformBotService(("owned-project",)),
    )

    text, keyboard = await handlers.handle_admin_callback(
        "delete:foreign-project",
        "123",
        pool=object(),
    )

    assert text == "Недостаточно прав для доступа к этому проекту."
    assert keyboard is not None


@pytest.mark.asyncio
async def test_owned_project_callback_reaches_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handlers,
        "_build_platform_bot_service",
        lambda pool: _FakePlatformBotService(("owned-project",)),
    )

    async def fake_project_handler(callback_data: str, chat_id: str, pool):
        assert callback_data == "project:owned-project"
        assert chat_id == "123"
        return "owned", None

    monkeypatch.setattr(handlers, "_handle_project_callback", fake_project_handler)
    monkeypatch.setattr(
        handlers,
        "PREFIX_CALLBACK_HANDLERS",
        (("project:", fake_project_handler),),
    )

    assert await handlers.handle_admin_callback(
        "project:owned-project",
        "123",
        pool=object(),
    ) == ("owned", None)
