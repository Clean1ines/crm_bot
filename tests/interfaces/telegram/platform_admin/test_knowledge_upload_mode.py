from __future__ import annotations

import pytest
from telegram import InlineKeyboardMarkup

from src.interfaces.telegram.platform_admin import handlers
from src.interfaces.telegram.platform_admin.keyboards import (
    make_knowledge_preprocessing_mode_keyboard,
)


def _callback_data_from_markup(reply_markup: InlineKeyboardMarkup | None) -> list[str]:
    assert reply_markup is not None
    return [
        button.callback_data or ""
        for row in reply_markup.inline_keyboard
        for button in row
    ]


@pytest.mark.asyncio
async def test_knowledge_callback_asks_for_preprocessing_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_clear_admin_state(chat_id: str) -> None:
        assert chat_id == "123"

    async def fake_project_access(
        *,
        chat_id: str,
        project_id: str,
        pool,
    ) -> bool:
        assert chat_id == "123"
        assert project_id == "project-1"
        assert pool is None
        return True

    monkeypatch.setattr(
        handlers,
        "clear_admin_state",
        fake_clear_admin_state,
    )
    monkeypatch.setattr(
        handlers,
        "_telegram_user_can_access_project",
        fake_project_access,
    )

    text, reply_markup = await handlers.handle_admin_callback(
        "knowledge:project-1",
        "123",
        pool=None,
    )

    assert "режим" in text.lower()
    assert "FAQ" in text
    assert "Прайс" in text

    callback_data = _callback_data_from_markup(reply_markup)
    assert "knowledge_mode:project-1:faq" in callback_data
    assert "knowledge_mode:project-1:price_list" in callback_data
    assert all(not callback.endswith(":plain") for callback in callback_data)
    assert all(not callback.endswith(":instruction") for callback in callback_data)


def test_knowledge_preprocessing_keyboard_exposes_only_supported_modes() -> None:
    keyboard = make_knowledge_preprocessing_mode_keyboard("project-1")
    callback_data = _callback_data_from_markup(keyboard)

    assert "knowledge_mode:project-1:faq" in callback_data
    assert "knowledge_mode:project-1:price_list" in callback_data
    assert all(not callback.endswith(":plain") for callback in callback_data)
    assert all(not callback.endswith(":instruction") for callback in callback_data)


def test_knowledge_preprocessing_keyboard_keeps_back_button() -> None:
    keyboard = make_knowledge_preprocessing_mode_keyboard("project-1")
    callback_data = _callback_data_from_markup(keyboard)

    assert "project:project-1" in callback_data
