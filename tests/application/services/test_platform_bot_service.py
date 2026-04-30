from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.platform_bot_service import PlatformBotService
from src.domain.control_plane.project_views import ProjectMemberView, ProjectSummaryView


@pytest.fixture
def service():
    svc = PlatformBotService(MagicMock())
    svc.user_repo = MagicMock()
    svc.project_repo = MagicMock()
    svc.project_repo.get_user_display_name = AsyncMock(return_value=None)
    return svc


@pytest.mark.asyncio
async def test_create_project_for_telegram_user_uses_canonical_user_id(service):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        return_value=("user-1", True)
    )
    service.project_repo.create_project_with_user_id = AsyncMock(
        return_value="project-1"
    )

    result = await service.create_project_for_telegram_user(123, "Acme")

    assert result == "project-1"
    service.project_repo.create_project_with_user_id.assert_awaited_once_with(
        "user-1", "Acme"
    )


@pytest.mark.asyncio
async def test_list_projects_for_telegram_user_uses_typed_membership_lookup(service):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        return_value=("user-1", False)
    )
    service.project_repo.get_projects_for_user_view = AsyncMock(
        return_value=[
            ProjectSummaryView.from_record(
                {
                    "id": "p1",
                    "name": "P1",
                    "is_pro_mode": False,
                    "user_id": "user-1",
                }
            )
        ]
    )

    result = await service.list_projects_for_telegram_user(123)

    assert [project.to_dict() for project in result.projects] == [
        {
            "id": "p1",
            "name": "P1",
            "is_pro_mode": False,
            "user_id": "user-1",
            "client_bot_username": None,
            "manager_bot_username": None,
            "access_role": None,
        }
    ]
    service.project_repo.get_projects_for_user_view.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
async def test_list_projects_for_telegram_user_creates_platform_user_when_missing(
    service,
):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        return_value=("user-1", True)
    )
    service.project_repo.get_projects_for_user_view = AsyncMock(return_value=[])

    result = await service.list_projects_for_telegram_user(123)

    assert result.projects == []
    service.project_repo.get_projects_for_user_view.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
async def test_add_manager_by_chat_id_links_existing_platform_user(service):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        side_effect=[
            ("owner-user", False),
            ("user-2", False),
        ]
    )
    service.project_repo.get_project_view = AsyncMock(
        return_value=ProjectSummaryView.from_record(
            {
                "id": "project-1",
                "name": "P1",
                "is_pro_mode": False,
                "user_id": "owner-user",
            }
        )
    )
    service.project_repo.get_project_member_role = AsyncMock(return_value=None)
    service.project_repo.get_user_display_name = AsyncMock(return_value="Alice Manager")
    service.project_repo.add_project_member = AsyncMock()

    result = await service.add_manager_by_chat_id("project-1", 123, "456")

    assert result == "Alice Manager добавлен как manager."
    service.project_repo.add_project_member.assert_awaited_once_with(
        "project-1", "user-2", "manager"
    )


@pytest.mark.asyncio
async def test_get_project_team_filters_project_member_roles(service):
    service.project_repo.get_project_members_view = AsyncMock(
        return_value=[
            ProjectMemberView.from_record(
                {"project_id": "project-1", "user_id": "u1", "role": "owner"}
            ),
            ProjectMemberView.from_record(
                {"project_id": "project-1", "user_id": "u2", "role": "manager"}
            ),
            ProjectMemberView.from_record(
                {"project_id": "project-1", "user_id": "u3", "role": "viewer"}
            ),
        ]
    )

    result = await service.get_project_team("project-1")

    assert result.to_dict() == {
        "members": [
            {
                "project_id": "project-1",
                "user_id": "u1",
                "role": "owner",
                "display_name": "Менеджер",
            },
            {
                "project_id": "project-1",
                "user_id": "u2",
                "role": "manager",
                "display_name": "Менеджер",
            },
        ],
        "legacy_targets": [],
    }


@pytest.mark.asyncio
async def test_add_manager_by_chat_id_owner_self_keeps_owner(service):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        side_effect=[
            ("owner-user", False),
            ("owner-user", False),
        ]
    )
    service.project_repo.get_project_view = AsyncMock(
        return_value=ProjectSummaryView.from_record(
            {
                "id": "project-1",
                "name": "P1",
                "is_pro_mode": False,
                "user_id": "owner-user",
            }
        )
    )
    service.project_repo.get_project_member_role = AsyncMock()
    service.project_repo.get_user_display_name = AsyncMock(return_value="Project Owner")
    service.project_repo.add_project_member = AsyncMock()

    result = await service.add_manager_by_chat_id("project-1", 123, "123")

    assert result == "Project Owner уже владелец проекта; роль owner сохранена."
    service.project_repo.add_project_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_manager_by_chat_id_owner_can_downgrade_admin_to_manager(service):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        side_effect=[
            ("owner-user", False),
            ("admin-user", False),
        ]
    )
    service.project_repo.get_project_view = AsyncMock(
        return_value=ProjectSummaryView.from_record(
            {
                "id": "project-1",
                "name": "P1",
                "is_pro_mode": False,
                "user_id": "owner-user",
            }
        )
    )
    service.project_repo.get_project_member_role = AsyncMock(return_value="admin")
    service.project_repo.get_user_display_name = AsyncMock(return_value="Admin User")
    service.project_repo.add_project_member = AsyncMock()

    result = await service.add_manager_by_chat_id("project-1", 123, "456")

    assert result == "Admin User добавлен как manager."
    service.project_repo.add_project_member.assert_awaited_once_with(
        "project-1", "admin-user", "manager"
    )


@pytest.mark.asyncio
async def test_add_manager_by_chat_id_admin_cannot_downgrade_owner(service):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        side_effect=[
            ("admin-user", False),
            ("owner-user", False),
        ]
    )
    service.project_repo.get_project_view = AsyncMock(
        return_value=ProjectSummaryView.from_record(
            {
                "id": "project-1",
                "name": "P1",
                "is_pro_mode": False,
                "user_id": "owner-user",
            }
        )
    )
    service.project_repo.get_project_member_role = AsyncMock(return_value="admin")
    service.project_repo.add_project_member = AsyncMock()

    result = await service.add_manager_by_chat_id("project-1", 456, "123")

    assert "admin не может понижать owner/admin" in result
    service.project_repo.add_project_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_manager_by_chat_id_admin_cannot_downgrade_admin(service):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        side_effect=[
            ("actor-admin", False),
            ("target-admin", False),
        ]
    )
    service.project_repo.get_project_view = AsyncMock(
        return_value=ProjectSummaryView.from_record(
            {
                "id": "project-1",
                "name": "P1",
                "is_pro_mode": False,
                "user_id": "owner-user",
            }
        )
    )
    service.project_repo.get_project_member_role = AsyncMock(
        side_effect=["admin", "admin"]
    )
    service.project_repo.add_project_member = AsyncMock()

    result = await service.add_manager_by_chat_id("project-1", 456, "789")

    assert "admin не может понижать owner/admin" in result
    service.project_repo.add_project_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_manager_by_chat_id_admin_can_add_plain_user_as_manager(service):
    service.user_repo.get_or_create_by_telegram = AsyncMock(
        side_effect=[
            ("admin-user", False),
            ("plain-user", False),
        ]
    )
    service.project_repo.get_project_view = AsyncMock(
        return_value=ProjectSummaryView.from_record(
            {
                "id": "project-1",
                "name": "P1",
                "is_pro_mode": False,
                "user_id": "owner-user",
            }
        )
    )
    service.project_repo.get_project_member_role = AsyncMock(
        side_effect=["admin", None]
    )
    service.project_repo.get_user_display_name = AsyncMock(return_value="Plain User")
    service.project_repo.add_project_member = AsyncMock()

    result = await service.add_manager_by_chat_id("project-1", 456, "789")

    assert result == "Plain User добавлен как manager."
    service.project_repo.add_project_member.assert_awaited_once_with(
        "project-1", "plain-user", "manager"
    )
