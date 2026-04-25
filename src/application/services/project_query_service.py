from typing import Any

from src.application.dto.control_plane_dto import ProjectMemberDto
from src.application.dto.project_dto import (
    ProjectChannelDto,
    ProjectConfigurationDto,
    ProjectIntegrationDto,
    ProjectSummaryDto,
)
from src.application.errors import NotFoundError
from src.domain.control_plane.project_configuration import ProjectConfigurationView


from src.domain.control_plane.project_views import ProjectMemberView, ProjectSummaryView
from src.domain.control_plane.roles import PROJECT_READ_ROLES


class ProjectQueryService:
    def __init__(self, repo: Any, access_service: Any) -> None:
        self.repo = repo
        self.access_service = access_service

    @staticmethod
    def _serialize_manager_targets(manager_targets: list[str]) -> list[int]:
        serialized: list[int] = []
        for manager_target in manager_targets:
            try:
                serialized.append(int(manager_target))
            except (TypeError, ValueError):
                continue
        return serialized

    async def _load_project_configuration_view(self, project_id: str) -> ProjectConfigurationView:
        return await self.repo.get_project_configuration_view(project_id)

    async def _load_project_view(self, project_id: str) -> ProjectSummaryView | None:
        return await self.repo.get_project_view(project_id)

    async def _load_projects_for_user_view(self, user_id: str) -> list[ProjectSummaryView]:
        return await self.repo.get_projects_for_user_view(user_id)

    async def _load_project_members_view(self, project_id: str) -> list[ProjectMemberView]:
        return await self.repo.get_project_members_view(project_id)

    async def list_projects(self, current_user_id: str):
        projects = await self._load_projects_for_user_view(current_user_id)
        return [ProjectSummaryDto.from_record(project.to_record()).to_dict() for project in projects]

    async def get_project(self, project_id: str, current_user_id: str):
        project = await self._load_project_view(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if project.user_id != current_user_id:
            await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        return ProjectSummaryDto.from_record(project.to_record()).to_dict()

    async def get_managers(self, project_id: str, current_user_id: str):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        return self._serialize_manager_targets(await self.repo.get_manager_notification_targets(project_id))

    async def list_project_members(self, project_id: str, current_user_id: str):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        members = await self._load_project_members_view(project_id)
        return [ProjectMemberDto.from_record(member.to_record()) for member in members]

    async def get_project_configuration(self, project_id: str, current_user_id: str):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        configuration = await self._load_project_configuration_view(project_id)
        return ProjectConfigurationDto.from_record(configuration.to_record()).to_dict()

    async def list_project_integrations(self, project_id: str, current_user_id: str):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        configuration = await self._load_project_configuration_view(project_id)
        return [
            ProjectIntegrationDto.from_record(integration.to_record()).to_dict()
            for integration in configuration.integrations
        ]

    async def list_project_channels(self, project_id: str, current_user_id: str):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        configuration = await self._load_project_configuration_view(project_id)
        return [
            ProjectChannelDto.from_record(channel.to_record()).to_dict()
            for channel in configuration.channels
        ]
