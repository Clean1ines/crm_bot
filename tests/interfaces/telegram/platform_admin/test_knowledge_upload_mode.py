from unittest.mock import AsyncMock

import pytest

from src.interfaces.telegram.platform_admin import handlers
from src.interfaces.telegram.platform_admin.knowledge_upload import (
    _queue_knowledge_upload,
)


@pytest.mark.asyncio
async def test_knowledge_callback_asks_for_preprocessing_mode(monkeypatch) -> None:
    clear_state = AsyncMock()
    monkeypatch.setattr(handlers, "_clear_state", clear_state)

    text, keyboard = await handlers.handle_admin_callback(
        "knowledge:project-1",
        "123",
        object(),
    )

    assert "Выберите режим обработки" in text
    assert keyboard is not None

    payload = keyboard.to_dict()
    callback_data = [
        button["callback_data"] for row in payload["inline_keyboard"] for button in row
    ]

    assert "knowledge_mode:project-1:plain" in callback_data
    assert "knowledge_mode:project-1:faq" in callback_data
    assert "knowledge_mode:project-1:price_list" in callback_data
    assert "knowledge_mode:project-1:instruction" in callback_data
    clear_state.assert_awaited_once_with("123")


@pytest.mark.asyncio
async def test_knowledge_mode_callback_stores_mode_and_awaits_file(
    monkeypatch,
) -> None:
    set_data = AsyncMock()
    set_state = AsyncMock()
    monkeypatch.setattr(handlers, "_set_data", set_data)
    monkeypatch.setattr(handlers, "_set_state", set_state)

    text, keyboard = await handlers.handle_admin_callback(
        "knowledge_mode:project-1:faq",
        "123",
        object(),
    )

    assert "Отправьте файл" in text
    assert "faq" in text
    assert keyboard is not None

    set_data.assert_awaited_once_with(
        "123",
        {"project_id": "project-1", "preprocessing_mode": "faq"},
    )
    set_state.assert_awaited_once_with("123", handlers.STATE_AWAIT_KNOWLEDGE_FILE)


@pytest.mark.asyncio
async def test_knowledge_mode_callback_rejects_unknown_mode(monkeypatch) -> None:
    clear_state = AsyncMock()
    monkeypatch.setattr(handlers, "_clear_state", clear_state)

    text, keyboard = await handlers.handle_admin_callback(
        "knowledge_mode:project-1:weird",
        "123",
        object(),
    )

    assert "Некорректный режим" in text
    assert keyboard is None
    clear_state.assert_awaited_once_with("123")


@pytest.mark.asyncio
async def test_queue_knowledge_upload_passes_selected_preprocessing_mode(
    monkeypatch,
) -> None:
    upload_call = AsyncMock()
    monkeypatch.setattr(
        "src.interfaces.telegram.platform_admin.knowledge_upload."
        "upload_platform_admin_knowledge_file",
        upload_call,
    )

    await _queue_knowledge_upload(
        pool=object(),
        project_id="project-1",
        filename="kb.md",
        file_content=b"content",
        preprocessing_mode="instruction",
    )

    assert upload_call.await_args.kwargs["project_id"] == "project-1"
    assert upload_call.await_args.kwargs["file_name"] == "kb.md"
    assert upload_call.await_args.kwargs["file_content"] == b"content"
    assert upload_call.await_args.kwargs["preprocessing_mode"] == "instruction"
