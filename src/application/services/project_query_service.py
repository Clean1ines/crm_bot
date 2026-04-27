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
from src.domain.control_plane.project_configuration import (
    ProjectChannelView,
    ProjectConfigurationView,
    ProjectIntegrationView,
    ProjectPromptVersionView,
)
from src.domain.control_plane.project_views import ProjectMemberView, ProjectSummaryView
from src.domain.control_plane.roles import PROJECT_READ_ROLES
from src.domain.project_plane.manager_reply_history import ManagerReplyHistoryItemView
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


def _integration_record(view: ProjectIntegrationView) -> JsonObject:
    return {
        "id": view.id,
        "project_id": view.project_id,
        "provider": view.provider,
        "status": view.status,
        "config_json": view.config_json,
        "credentials_encrypted": view.credentials_encrypted,
        "created_at": view.created_at,
        "updated_at": view.updated_at,
    }

def _channel_record(view: ProjectChannelView) -> JsonObject:
    return {
        "id": view.id,
        "project_id": view.project_id,
        "kind": view.kind,
        "provider": view.provider,
        "status": view.status,
        "config_json": view.config_json,
        "created_at": view.created_at,
        "updated_at": view.updated_at,
    }

def _prompt_version_record(view: ProjectPromptVersionView) -> JsonObject:
    return {
        "id": view.id,
        "name": view.name,
        "prompt_json": view.prompt_json,
        "version": view.version,
        "is_active": view.is_active,
        "created_at": view.created_at,
        "updated_at": view.updated_at,
    }


def _configuration_record(view: ProjectConfigurationView) -> JsonObject:
    return {
        "project_id": view.project_id,
        "settings": view.settings,
        "policies": view.policies,
        "limit_profile": view.limit_profile,
        "integrations": [_integration_record(item) for item in view.integrations],
        "channels": [_channel_record(item) for item in view.channels],
        "prompt_versions": [_prompt_version_record(item) for item in view.prompt_versions],
    }


def _manager_reply_history_record(view: ManagerReplyHistoryItemView) -> JsonObject:
    return {
        "id": view.id,
        "thread_id": view.thread_id,
        "project_id": view.project_id,
        "manager_user_id": view.manager_user_id,
        "manager_chat_id": view.manager_chat_id,
        "text": view.text,
        "created_at": view.created_at,
    }


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

    async def _load_project_configuration_view(self, project_id: str) -> ProjectConfigurationView:
        return await self.repo.get_project_configuration_view(project_id)

    async def _load_project_view(self, project_id: str) -> ProjectSummaryView | None:
        return await self.repo.get_project_view(project_id)

    async def _load_projects_for_user_view(self, user_id: str) -> list[ProjectSummaryView]:
        return await self.repo.get_projects_for_user_view(user_id)

    async def _load_project_members_view(self, project_id: str) -> list[ProjectMemberView]:
        return await self.repo.get_project_members_view(project_id)

    async def list_projects(self, current_user_id: str) -> list[JsonObject]:
        projects = await self._load_projects_for_user_view(current_user_id)
        return [ProjectSummaryDto.from_record(_project_summary_record(project)).to_dict() for project in projects]

    async def get_project(self, project_id: str, current_user_id: str) -> JsonObject:
        project = await self._load_project_view(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if project.user_id != current_user_id:
            await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        return ProjectSummaryDto.from_record(_project_summary_record(project)).to_dict()

    async def get_managers(self, project_id: str, current_user_id: str) -> list[int]:
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        return self._serialize_manager_targets(await self.repo.get_manager_notification_targets(project_id))

    async def list_project_members(self, project_id: str, current_user_id: str) -> list[ProjectMemberDto]:
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        members = await self._load_project_members_view(project_id)
        return [ProjectMemberDto.from_record(_project_member_record(member)) for member in members]

    async def get_project_configuration(self, project_id: str, current_user_id: str) -> JsonObject:
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        configuration = await self._load_project_configuration_view(project_id)
        return ProjectConfigurationDto.from_record(_configuration_record(configuration)).to_dict()

    async def list_project_integrations(self, project_id: str, current_user_id: str) -> list[JsonObject]:
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        configuration = await self._load_project_configuration_view(project_id)
        return [
            ProjectIntegrationDto.from_record(_integration_record(integration)).to_dict()
            for integration in configuration.integrations
        ]

    async def list_project_channels(self, project_id: str, current_user_id: str) -> list[JsonObject]:
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
        configuration = await self._load_project_configuration_view(project_id)
        return [
            ProjectChannelDto.from_record(_channel_record(channel)).to_dict()
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
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)

        items = await self.event_reader.get_manager_reply_history(
            project_id=project_id,
            manager_user_id=manager_user_id,
            limit=limit,
            offset=offset,
        )

        return ManagerReplyHistoryDto.from_records(
            [_manager_reply_history_record(item) for item in items],
            limit=limit,
            offset=offset,
        ).to_dict()
