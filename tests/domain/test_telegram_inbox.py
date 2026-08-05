from __future__ import annotations

from uuid import uuid4

import pytest

from src.domain.telegram_inbox import (
    TelegramUpdateIdentity,
    TelegramUpdateSurface,
)


def test_direct_project_identity_construction_normalizes_valid_values() -> None:
    project_id = uuid4()

    identity = TelegramUpdateIdentity(
        surface=TelegramUpdateSurface.CLIENT,
        project_id=project_id,
        platform_scope=None,
        telegram_bot_id=123,
        telegram_update_id=0,
    )

    assert identity.surface is TelegramUpdateSurface.CLIENT
    assert identity.project_id == str(project_id)
    assert identity.platform_scope is None
    assert identity.telegram_bot_id == 123
    assert identity.telegram_update_id == 0


@pytest.mark.parametrize(
    "kwargs, error_type",
    [
        (
            {
                "surface": TelegramUpdateSurface.CLIENT,
                "project_id": None,
                "platform_scope": None,
                "telegram_bot_id": 1,
                "telegram_update_id": 1,
            },
            ValueError,
        ),
        (
            {
                "surface": TelegramUpdateSurface.MANAGER,
                "project_id": str(uuid4()),
                "platform_scope": "platform_admin",
                "telegram_bot_id": 1,
                "telegram_update_id": 1,
            },
            ValueError,
        ),
        (
            {
                "surface": TelegramUpdateSurface.CLIENT,
                "project_id": "not-a-uuid",
                "platform_scope": None,
                "telegram_bot_id": 1,
                "telegram_update_id": 1,
            },
            ValueError,
        ),
        (
            {
                "surface": TelegramUpdateSurface.PLATFORM_ADMIN,
                "project_id": str(uuid4()),
                "platform_scope": "platform_admin",
                "telegram_bot_id": 1,
                "telegram_update_id": 1,
            },
            ValueError,
        ),
        (
            {
                "surface": TelegramUpdateSurface.PLATFORM_ADMIN,
                "project_id": None,
                "platform_scope": "   ",
                "telegram_bot_id": 1,
                "telegram_update_id": 1,
            },
            ValueError,
        ),
        (
            {
                "surface": TelegramUpdateSurface.CLIENT,
                "project_id": str(uuid4()),
                "platform_scope": None,
                "telegram_bot_id": 0,
                "telegram_update_id": 1,
            },
            ValueError,
        ),
        (
            {
                "surface": TelegramUpdateSurface.CLIENT,
                "project_id": str(uuid4()),
                "platform_scope": None,
                "telegram_bot_id": True,
                "telegram_update_id": 1,
            },
            TypeError,
        ),
        (
            {
                "surface": TelegramUpdateSurface.CLIENT,
                "project_id": str(uuid4()),
                "platform_scope": None,
                "telegram_bot_id": 1,
                "telegram_update_id": -1,
            },
            ValueError,
        ),
        (
            {
                "surface": TelegramUpdateSurface.CLIENT,
                "project_id": str(uuid4()),
                "platform_scope": None,
                "telegram_bot_id": 1,
                "telegram_update_id": False,
            },
            TypeError,
        ),
    ],
)
def test_direct_identity_construction_rejects_invalid_values(
    kwargs,
    error_type,
) -> None:
    with pytest.raises(error_type):
        TelegramUpdateIdentity(**kwargs)
