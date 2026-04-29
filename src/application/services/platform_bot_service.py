from __future__ import annotations

from typing import cast

from src.application.dto.control_plane_dto import (
    ProjectMemberDto,
    ProjectTeamDto,
    TelegramAdminProjectsDto,
)
from src.application.dto.project_dto import ProjectSummaryDto
from src.application.ports.project_port import ProjectControlPort
from src.application.ports.user_port import UserAuthPort
from src.domain.control_plane.memberships import is_manager_capable_role
from src.domain.control_plane.roles import PROJECT_ADMIN, PROJECT_MANAGER, PROJECT_OWNER


class PlatformBotService:
    """
    Control-plane application service for the platform Telegram bot.

    It centralizes project/member operations so the Telegram handler stays a
    transport adapter instead of carrying domain decisions directly.
    """

    def __init__(
        self, user_repo: UserAuthPort, project_repo: ProjectControlPort | None = None
    ) -> None:
        self.user_repo = user_repo
        if project_repo is None:
            self.project_repo = cast(
                ProjectControlPort,
                getattr(user_repo, "project_repo", user_repo),
            )
            return

        self.project_repo = project_repo

    async def create_project_for_telegram_user(
        self, telegram_chat_id: int, name: str
    ) -> str:
        user_id, _ = await self.user_repo.get_or_create_by_telegram(
            telegram_chat_id, first_name="", username=None
        )
        return await self.project_repo.create_project_with_user_id(user_id, name)

    async def list_projects_for_telegram_user(
        self, telegram_chat_id: int
    ) -> TelegramAdminProjectsDto:
        user_id, _ = await self.user_repo.get_or_create_by_telegram(
            telegram_chat_id, first_name="", username=None
        )
        projects = await self.project_repo.get_projects_for_user_view(user_id)
        return TelegramAdminProjectsDto.create(
            [ProjectSummaryDto.from_view(project) for project in projects]
        )

    async def _effective_project_role(
        self, project_id: str, user_id: str
    ) -> str | None:
        project = await self.project_repo.get_project_view(project_id)
        if project is None:
            raise ValueError("Project not found")

        if project.user_id == user_id:
            return PROJECT_OWNER

        return await self.project_repo.get_project_member_role(project_id, user_id)

    async def add_manager_by_chat_id(
        self,
        project_id: str,
        actor_telegram_chat_id: int,
        manager_chat_id: str,
    ) -> str:
        target_telegram_chat_id = int(manager_chat_id.strip())

        actor_user_id, _ = await self.user_repo.get_or_create_by_telegram(
            actor_telegram_chat_id, first_name="", username=None
        )
        target_user_id, _ = await self.user_repo.get_or_create_by_telegram(
            target_telegram_chat_id, first_name="", username=None
        )

        actor_role = await self._effective_project_role(project_id, actor_user_id)
        target_role = await self._effective_project_role(project_id, target_user_id)
        target_label = await self._member_display_name(target_user_id, "Менеджер")

        if actor_role == PROJECT_OWNER and target_role == PROJECT_OWNER:
            return f"{target_label} уже владелец проекта; роль owner сохранена."

        if actor_role == PROJECT_ADMIN and target_role in {
            PROJECT_OWNER,
            PROJECT_ADMIN,
        }:
            return "Недостаточно прав: admin не может понижать owner/admin до manager."

        if actor_role not in {PROJECT_OWNER, PROJECT_ADMIN}:
            return "Недостаточно прав: только owner/admin могут назначать менеджеров."

        if target_role == PROJECT_MANAGER:
            return f"{target_label} уже имеет роль manager."

        await self.project_repo.add_project_member(
            project_id, target_user_id, PROJECT_MANAGER
        )
        return f"{target_label} добавлен как manager."

    async def _member_display_name(self, user_id: str, fallback: str) -> str:
        display_name = await self.project_repo.get_user_display_name(user_id)
        return display_name or fallback

    async def get_project_team(self, project_id: str) -> ProjectTeamDto:
        members = await self.project_repo.get_project_members_view(project_id)
        manager_capable_members = [
            ProjectMemberDto.from_view(member)
            for member in members
            if is_manager_capable_role(member.role)
        ]
        return ProjectTeamDto.create(members=manager_capable_members, legacy_targets=[])
