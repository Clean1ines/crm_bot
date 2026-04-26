from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.interfaces.telegram.platform_admin.handlers import (
    STATE_AWAIT_ADD_MANAGER,
    STATE_DELETE_AWAIT_CONFIRM,
    _process_admin_step,
)
from src.interfaces.telegram.platform_admin.knowledge_upload import handle_knowledge_upload


@pytest.mark.asyncio
async def test_add_manager_failure_returns_safe_message_without_raw_exception():
    with (
        patch("src.interfaces.telegram.platform_admin.handlers._get_data", AsyncMock(return_value={"project_id": "project-1"})),
        patch("src.interfaces.telegram.platform_admin.handlers._clear_state", AsyncMock()),
        patch("src.interfaces.telegram.platform_admin.handlers._get_project_menu_keyboard", AsyncMock(return_value=None)),
        patch("src.interfaces.telegram.platform_admin.handlers.PlatformBotService") as Service,
        patch("src.interfaces.telegram.platform_admin.handlers.logger") as logger,
    ):
        service = MagicMock()
        service.add_manager_by_chat_id = AsyncMock(side_effect=RuntimeError("internal db details"))
        Service.return_value = service

        text, keyboard = await _process_admin_step(
            "12345",
            {},
            MagicMock(),
            chat_id="111",
            state=STATE_AWAIT_ADD_MANAGER,
        )

    assert text == "Ошибка при добавлении менеджера. Попробуйте позже."
    assert keyboard is None
    assert "internal db details" not in text
    logger.exception.assert_called_once()
    assert logger.exception.call_args.kwargs["extra"]["policy"] == "safe_user_fallback"


@pytest.mark.asyncio
async def test_delete_project_failure_returns_safe_message_without_raw_exception():
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value.execute = AsyncMock(
        side_effect=RuntimeError("delete constraint internals")
    )

    with (
        patch("src.interfaces.telegram.platform_admin.handlers._get_data", AsyncMock(return_value={"project_id": "11111111-1111-1111-1111-111111111111", "project_name": "Acme"})),
        patch("src.interfaces.telegram.platform_admin.handlers._clear_state", AsyncMock()),
        patch("src.interfaces.telegram.platform_admin.handlers.logger") as logger,
    ):
        text, keyboard = await _process_admin_step(
            "да",
            {},
            pool,
            chat_id="111",
            state=STATE_DELETE_AWAIT_CONFIRM,
        )

    assert text == "Ошибка при удалении проекта. Попробуйте позже."
    assert keyboard is None
    assert "delete constraint internals" not in text
    logger.exception.assert_called_once()
    assert logger.exception.call_args.kwargs["extra"]["policy"] == "safe_user_fallback"


@pytest.mark.asyncio
async def test_knowledge_upload_failure_returns_safe_fallback_and_logs_context():
    with (
        patch("src.interfaces.telegram.platform_admin.knowledge_upload._get_data", AsyncMock(return_value={"project_id": "project-1"})),
        patch("src.interfaces.telegram.platform_admin.knowledge_upload._get_file_path", AsyncMock(side_effect=RuntimeError("telegram token internals"))),
        patch("src.interfaces.telegram.platform_admin.knowledge_upload._clear_state", AsyncMock()),
        patch("src.interfaces.telegram.platform_admin.knowledge_upload._get_project_menu_keyboard", AsyncMock(return_value=None)),
        patch("src.interfaces.telegram.platform_admin.knowledge_upload.logger") as logger,
    ):
        text, keyboard = await handle_knowledge_upload(
            "111",
            {"document": {"file_id": "file-1", "file_name": "kb.txt"}},
            MagicMock(),
        )

    assert text == "Ошибка при обработке файла. Попробуйте другой файл или проверьте формат."
    assert keyboard is None
    assert "telegram token internals" not in text
    logger.exception.assert_called_once()
    assert logger.exception.call_args.kwargs["extra"]["policy"] == "safe_user_fallback"
