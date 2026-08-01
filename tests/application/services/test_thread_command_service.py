from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.services.thread_command_service import ThreadCommandService


PROJECT_ID = str(uuid4())
THREAD_ID = str(uuid4())
USER_ID = str(uuid4())


def _service(
    *,
    platform_admin: bool = False,
    project_owner: bool = False,
    member_role: str | None = "admin",
    thread_status: str = "active",
    active_thread: str | None = THREAD_ID,
    user_exists: bool = True,
    client_exists: bool = True,
):
    lifecycle = AsyncMock()
    lifecycle.get_or_create_client = AsyncMock(return_value="client-1")
    lifecycle.find_client = AsyncMock(
        return_value="client-1" if client_exists else None
    )
    lifecycle.get_active_thread = AsyncMock(return_value=active_thread)
    lifecycle.update_status = AsyncMock()

    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(
        return_value=SimpleNamespace(status=thread_status)
    )

    effective_role = "owner" if project_owner else member_role
    access = AsyncMock()
    access.resolve_effective_project_role = AsyncMock(return_value=effective_role)

    users = AsyncMock()
    users.get_or_create_by_telegram = AsyncMock(return_value=(USER_ID, False))
    users.get_user_by_identity_view = AsyncMock(
        return_value=SimpleNamespace(id=USER_ID) if user_exists else None
    )
    users.is_platform_admin = AsyncMock(return_value=platform_admin)

    events = AsyncMock()

    service = ThreadCommandService(
        lifecycle,
        AsyncMock(),
        thread_read_repo=read,
        event_repo=events,
        project_access_service=access,
        user_repo=users,
    )
    return service, lifecycle, read, access, users, events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "actor_role"),
    [
        ({"platform_admin": True, "member_role": None}, "platform_admin"),
        ({"project_owner": True, "member_role": None}, "owner"),
        ({"member_role": "admin"}, "admin"),
    ],
)
async def test_reset_dialog_allows_platform_owner_project_owner_and_admin(
    kwargs, actor_role
):
    service, lifecycle, _read, _repo, _users, events = _service(**kwargs)

    result = await service.reset_dialog_by_telegram_admin(
        project_id=PROJECT_ID,
        chat_id=123,
        actor_telegram_id=456,
        username="admin",
        full_name="Admin",
    )

    assert result == "Диалог сброшен. Следующее сообщение начнёт новый диалог."
    lifecycle.get_or_create_client.assert_not_awaited()
    lifecycle.find_client.assert_awaited_once_with(PROJECT_ID, 123, source="telegram")
    lifecycle.get_active_thread.assert_awaited_once_with("client-1")
    lifecycle.update_status.assert_awaited_once_with(THREAD_ID, "closed")
    payload = events.append.await_args.kwargs["payload"]
    assert payload == {
        "actor_user_id": USER_ID,
        "actor_role": actor_role,
        "project_id": PROJECT_ID,
        "thread_id": THREAD_ID,
        "reason": "admin_test_reset",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("member_role", ["manager", "viewer", None])
async def test_reset_dialog_denies_non_admin_project_roles(member_role):
    service, lifecycle, _read, _repo, users, events = _service(member_role=member_role)

    result = await service.reset_dialog_by_telegram_admin(
        project_id=PROJECT_ID,
        chat_id=123,
        actor_telegram_id=456,
    )

    assert "доступна только владельцу или администратору" in result
    lifecycle.get_or_create_client.assert_not_awaited()
    lifecycle.find_client.assert_not_awaited()
    lifecycle.update_status.assert_not_awaited()
    users.get_or_create_by_telegram.assert_not_awaited()
    events.append.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_dialog_returns_no_active_thread_without_graph_or_memory_work():
    service, lifecycle, _read, _repo, _users, events = _service(active_thread=None)

    result = await service.reset_dialog_by_telegram_admin(
        project_id=PROJECT_ID,
        chat_id=123,
        actor_telegram_id=456,
    )

    assert result == "Активный диалог не найден."
    lifecycle.get_or_create_client.assert_not_awaited()
    lifecycle.find_client.assert_awaited_once()
    lifecycle.update_status.assert_not_awaited()
    events.append.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_dialog_returns_no_active_thread_without_creating_client():
    service, lifecycle, _read, _access, users, events = _service(client_exists=False)

    result = await service.reset_dialog_by_telegram_admin(
        project_id=PROJECT_ID,
        chat_id=123,
        actor_telegram_id=456,
    )

    assert result == "Активный диалог не найден."
    users.get_or_create_by_telegram.assert_not_awaited()
    lifecycle.get_or_create_client.assert_not_awaited()
    lifecycle.get_active_thread.assert_not_awaited()
    events.append.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_dialog_unknown_telegram_user_has_no_create_side_effects():
    service, lifecycle, _read, access, users, events = _service(user_exists=False)

    result = await service.reset_dialog_by_telegram_admin(
        project_id=PROJECT_ID,
        chat_id=123,
        actor_telegram_id=456,
    )

    assert "доступна только владельцу или администратору" in result
    users.get_or_create_by_telegram.assert_not_awaited()
    access.resolve_effective_project_role.assert_not_awaited()
    lifecycle.get_or_create_client.assert_not_awaited()
    lifecycle.find_client.assert_not_awaited()
    events.append.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("thread_status", ["waiting_manager", "manual"])
async def test_reset_dialog_rejects_manager_controlled_thread_without_closing_it(
    thread_status,
):
    service, lifecycle, _read, _repo, _users, events = _service(
        thread_status=thread_status
    )

    result = await service.reset_dialog_by_telegram_admin(
        project_id=PROJECT_ID,
        chat_id=123,
        actor_telegram_id=456,
    )

    assert "передан менеджеру" in result
    lifecycle.update_status.assert_not_awaited()
    events.append.assert_not_awaited()
