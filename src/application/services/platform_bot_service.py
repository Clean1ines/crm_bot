from __future__ import annotations

from src.application.dto.control_plane_dto import (
    ProjectMemberDto,
    ProjectTeamDto,
    TelegramAdminProjectsDto,
)
from src.application.dto.project_dto import ProjectSummaryDto
from src.application.ports.project_port import ProjectControlPort
from src.application.ports.user_port import UserAuthPort
from src.domain.control_plane.memberships import is_manager_capable_role
from src.domain.control_plane.project_views import ProjectMemberView, ProjectSummaryView
from src.domain.project_plane.json_types import JsonObject


def _project_summary_record(view: ProjectSummaryView) -> JsonObject:
    return {
        "id": view.id,
        "user_id": view.user_id,
        "name": view.name,
        "is_pro_mode": view.is_pro_mode,
        "created_at": view.created_at,
        "updated_at": view.updated_at,
        "client_bot_username": view.client_bot_username,
        "manager_bot_username": view.manager_bot_username,
        "access_role": getattr(view, "access_role", None),
    }


def _project_member_record(view: ProjectMemberView) -> JsonObject:
    return {
        "id": getattr(view, "id", None),
        "project_id": getattr(view, "project_id", None),
        "user_id": view.user_id,
        "role": view.role,
        "created_at": getattr(view, "created_at", None),
        "telegram_id": getattr(view, "telegram_id", None),
        "username": getattr(view, "username", None),
        "full_name": getattr(view, "full_name", None),
        "email": getattr(view, "email", None),
    }


class PlatformBotService:
    """
    Control-plane application service for the platform Telegram bot.

    It centralizes project/member operations so the Telegram handler stays a
    transport adapter instead of carrying domain decisions directly.
    """

    def __init__(self, user_repo: UserAuthPort, project_repo: ProjectControlPort | None = None) -> None:
        if project_repo is None:
            self.user_repo = user_repo
            self.project_repo = getattr(user_repo, "project_repo", user_repo)
            return

        self.user_repo = user_repo
        self.project_repo = project_repo

    async def create_project_for_telegram_user(self, telegram_chat_id: int, name: str) -> str:
        user_id, _ = await self.user_repo.get_or_create_by_telegram(
            telegram_chat_id, first_name="", username=None
        )
        return await self.project_repo.create_project_with_user_id(user_id, name)

    async def list_projects_for_telegram_user(self, telegram_chat_id: int) -> TelegramAdminProjectsDto:
        user_id, _ = await self.user_repo.get_or_create_by_telegram(
            telegram_chat_id, first_name="", username=None
        )
        projects = await self.project_repo.get_projects_for_user_view(user_id)
        return TelegramAdminProjectsDto.create(
            [ProjectSummaryDto.from_record(_project_summary_record(project)) for project in projects]
        )

    async def add_manager_by_chat_id(self, project_id: str, manager_chat_id: str) -> str:
        normalized_manager_id = manager_chat_id.strip()
        user_id, _ = await self.user_repo.get_or_create_by_telegram(
            int(normalized_manager_id), first_name="", username=None
        )
        await self.project_repo.add_project_member(project_id, user_id, "manager")
        return f"Пользователь {normalized_manager_id} добавлен как manager (platform user: {user_id})."

    async def get_project_team(self, project_id: str) -> ProjectTeamDto:
        members = await self.project_repo.get_project_members_view(project_id)
        manager_capable_members = [
            ProjectMemberDto.from_record(_project_member_record(member))
            for member in members
            if is_manager_capable_role(member.role)
        ]
        return ProjectTeamDto.create(members=manager_capable_members, legacy_targets=[])
