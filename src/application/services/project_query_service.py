from src.application.dto.control_plane_dto import ProjectMemberDto
from src.application.dto.project_dto import (
    ManagerReplyHistoryDto,
    ProjectChannelDto,
    ProjectConfigurationDto,
    ProjectIntegrationDto,
    ProjectSummaryDto,
)
from src.application.errors import NotFoundError
from src.application.ports.event_port import EventReaderPort
from src.application.ports.project_port import ProjectAccessPort, ProjectReadPort
from src.domain.control_plane.project_configuration import ProjectConfigurationView
from src.domain.control_plane.project_views import ProjectMemberView, ProjectSummaryView
from src.domain.control_plane.roles import PROJECT_READ_ROLES
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


class ProjectQueryService:
    def __init__(
        self,
        repo: ProjectReadPort,
        access_service: ProjectAccessPort,
        event_reader: EventReaderPort,
    ) -> None:
        self.repo = repo
        self.access_service = access_service
        self.event_reader = event_reader

    @staticmethod
    def _serialize_manager_targets(manager_targets: list[str]) -> list[int]:
        serialized: list[int] = []
        for manager_target in manager_targets:
            try:
                serialized.append(int(manager_target))
            except (TypeError, ValueError):
                continue
        return serialized

    async def _load_project_configuration_view(
        self, project_id: str
    ) -> ProjectConfigurationView:
        return await self.repo.get_project_configuration_view(project_id)

    async def _load_project_view(self, project_id: str) -> ProjectSummaryView | None:
        return await self.repo.get_project_view(project_id)

    async def _load_projects_for_user_view(
        self, user_id: str
    ) -> list[ProjectSummaryView]:
        return await self.repo.get_projects_for_user_view(user_id)

    async def _load_project_members_view(
        self, project_id: str
    ) -> list[ProjectMemberView]:
        return await self.repo.get_project_members_view(project_id)

    async def list_projects(self, current_user_id: str) -> list[JsonObject]:
        projects = await self._load_projects_for_user_view(current_user_id)
        return [
            json_object_from_unknown(ProjectSummaryDto.from_view(project).to_dict())
            for project in projects
        ]

    async def get_project(self, project_id: str, current_user_id: str) -> JsonObject:
        project = await self._load_project_view(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if project.user_id != current_user_id:
            await self.access_service.require_project_role(
                project_id, current_user_id, PROJECT_READ_ROLES
            )
        return json_object_from_unknown(ProjectSummaryDto.from_view(project).to_dict())

    async def get_managers(self, project_id: str, current_user_id: str) -> list[int]:
        await self.access_service.require_project_role(
            project_id, current_user_id, PROJECT_READ_ROLES
        )
        return self._serialize_manager_targets(
            await self.repo.get_manager_notification_targets(project_id)
        )

    async def list_project_members(
        self, project_id: str, current_user_id: str
    ) -> list[ProjectMemberDto]:
        await self.access_service.require_project_role(
            project_id, current_user_id, PROJECT_READ_ROLES
        )
        members = await self._load_project_members_view(project_id)
        return [ProjectMemberDto.from_view(member) for member in members]

    async def get_project_configuration(
        self, project_id: str, current_user_id: str
    ) -> JsonObject:
        await self.access_service.require_project_role(
            project_id, current_user_id, PROJECT_READ_ROLES
        )
        configuration = await self._load_project_configuration_view(project_id)
        return json_object_from_unknown(
            ProjectConfigurationDto.from_view(configuration).to_dict()
        )

    async def list_project_integrations(
        self, project_id: str, current_user_id: str
    ) -> list[JsonObject]:
        await self.access_service.require_project_role(
            project_id, current_user_id, PROJECT_READ_ROLES
        )
        configuration = await self._load_project_configuration_view(project_id)
        return [
            json_object_from_unknown(
                ProjectIntegrationDto.from_view(integration).to_dict()
            )
            for integration in configuration.integrations
        ]

    async def list_project_channels(
        self, project_id: str, current_user_id: str
    ) -> list[JsonObject]:
        await self.access_service.require_project_role(
            project_id, current_user_id, PROJECT_READ_ROLES
        )
        configuration = await self._load_project_configuration_view(project_id)
        return [
            json_object_from_unknown(ProjectChannelDto.from_view(channel).to_dict())
            for channel in configuration.channels
        ]

    async def get_manager_reply_history(
        self,
        project_id: str,
        current_user_id: str,
        manager_user_id: str,
        limit: int,
        offset: int,
    ) -> JsonObject:
        await self.access_service.require_project_role(
            project_id, current_user_id, PROJECT_READ_ROLES
        )

        items = await self.event_reader.get_manager_reply_history(
            project_id=project_id,
            manager_user_id=manager_user_id,
            limit=limit,
            offset=offset,
        )

        return json_object_from_unknown(
            ManagerReplyHistoryDto.from_views(
                items,
                limit=limit,
                offset=offset,
            ).to_dict()
        )
