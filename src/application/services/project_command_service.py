from typing import Any

from src.domain.control_plane.project_views import ProjectSummaryView

from src.application.dto.control_plane_dto import ProjectMutationResultDto
from src.application.dto.project_dto import (
    ProjectChannelDto,
    ProjectConfigurationDto,
    ProjectIntegrationDto,
    ProjectSummaryDto,
)
from src.application.errors import InternalServiceError, NotFoundError, ValidationError
from src.application.services.project_query_service import ProjectQueryService
from src.domain.control_plane.roles import (
    ALLOWED_CHANNEL_KINDS,
    ALLOWED_PROJECT_ROLES,
    CHANNEL_CLIENT,
    CHANNEL_MANAGER,
    PROJECT_OWNER,
    PROJECT_WRITE_ROLES,
)


class ProjectCommandService:
    def __init__(
        self,
        repo: Any,
        access_service: Any,
        query_service: ProjectQueryService,
    ) -> None:
        self.repo = repo
        self.access_service = access_service
        self.query_service = query_service

    @staticmethod
    def _ensure_project_payload(project: ProjectSummaryView | None) -> dict:
        if project is None:
            raise InternalServiceError("Project operation failed")
        return ProjectSummaryDto.from_record(project.to_record()).to_dict()

    async def _require_existing_project(self, project_id: str) -> None:
        if not await self.repo.project_exists(project_id):
            raise NotFoundError("Project not found")

    async def create_project(self, current_user_id: str, name: str):
        project_id = await self.repo.create_project_with_user_id(current_user_id, name)
        project = await self.query_service._load_project_view(project_id)
        if not project:
            raise InternalServiceError("Project creation failed")
        return self._ensure_project_payload(project)

    async def update_project(self, project_id: str, current_user_id: str, name: str | None):
        await self._require_existing_project(project_id)
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.update_project(project_id, name)
        updated = await self.query_service._load_project_view(project_id)
        return self._ensure_project_payload(updated)

    async def delete_project(self, project_id: str, current_user_id: str) -> None:
        await self._require_existing_project(project_id)
        await self.access_service.require_project_role(project_id, current_user_id, [PROJECT_OWNER])
        await self.repo.delete_project(project_id)

    async def set_client_bot_token(self, project_id: str, current_user_id: str, token: str):
        await self._require_existing_project(project_id)
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.set_bot_token(project_id, token)
        await self.repo.upsert_project_channel(
            project_id,
            kind=CHANNEL_CLIENT,
            provider="telegram",
            status="active",
            config_json={"token_configured": True},
        )
        return ProjectMutationResultDto.create(status="ok")

    async def set_manager_bot_token(self, project_id: str, current_user_id: str, token: str):
        await self._require_existing_project(project_id)
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.set_manager_bot_token(project_id, token)
        await self.repo.upsert_project_channel(
            project_id,
            kind=CHANNEL_MANAGER,
            provider="telegram",
            status="active",
            config_json={"token_configured": True},
        )
        return ProjectMutationResultDto.create(status="ok")

    async def clear_client_bot_token(self, project_id: str, current_user_id: str):
        await self._require_existing_project(project_id)
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.set_bot_token(project_id, None)
        await self.repo.upsert_project_channel(
            project_id,
            kind=CHANNEL_CLIENT,
            provider="telegram",
            status="disabled",
            config_json={"token_configured": False},
        )
        return ProjectMutationResultDto.create(status="ok", type=CHANNEL_CLIENT)

    async def clear_manager_bot_token(self, project_id: str, current_user_id: str):
        await self._require_existing_project(project_id)
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.set_manager_bot_token(project_id, None)
        await self.repo.upsert_project_channel(
            project_id,
            kind=CHANNEL_MANAGER,
            provider="telegram",
            status="disabled",
            config_json={"token_configured": False},
        )
        return ProjectMutationResultDto.create(status="ok", type=CHANNEL_MANAGER)

    async def add_manager(self, project_id: str, current_user_id: str, chat_id: int):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        result = await self.repo.add_manager_by_telegram_identity(project_id, str(chat_id))
        return ProjectMutationResultDto.from_record(result)

    async def remove_manager(self, project_id: str, current_user_id: str, chat_id: int) -> None:
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.remove_manager_by_telegram_identity(project_id, str(chat_id))

    async def connect_bot(self, project_id: str, current_user_id: str, token: str, bot_type: str):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        if bot_type == CHANNEL_CLIENT:
            await self.repo.set_bot_token(project_id, token)
            await self.repo.upsert_project_channel(
                project_id,
                kind=CHANNEL_CLIENT,
                provider="telegram",
                status="active",
                config_json={"token_configured": True},
            )
        elif bot_type == CHANNEL_MANAGER:
            await self.repo.set_manager_bot_token(project_id, token)
            await self.repo.upsert_project_channel(
                project_id,
                kind=CHANNEL_MANAGER,
                provider="telegram",
                status="active",
                config_json={"token_configured": True},
            )
        else:
            raise ValidationError("Invalid bot type")
        return ProjectMutationResultDto.create(status="ok", type=bot_type)

    async def upsert_project_member(self, project_id: str, current_user_id: str, user_id: str, role: str):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        if role not in ALLOWED_PROJECT_ROLES:
            raise ValidationError("Invalid project role")
        await self.repo.add_project_member(project_id, user_id, role)
        return ProjectMutationResultDto.create(status="ok", user_id=user_id, role=role)

    async def delete_project_member(self, project_id: str, current_user_id: str, member_user_id: str) -> None:
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.remove_project_member(project_id, member_user_id)

    async def update_project_settings(self, project_id: str, current_user_id: str, data: dict):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.update_project_settings(project_id, data)
        configuration = await self.query_service._load_project_configuration_view(project_id)
        return ProjectConfigurationDto.from_record(configuration.to_record()).to_dict()

    async def update_project_policies(self, project_id: str, current_user_id: str, data: dict):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.update_project_policies(project_id, data)
        configuration = await self.query_service._load_project_configuration_view(project_id)
        return ProjectConfigurationDto.from_record(configuration.to_record()).to_dict()

    async def update_project_limit_profile(self, project_id: str, current_user_id: str, data: dict):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        await self.repo.update_project_limit_profile(project_id, data)
        configuration = await self.query_service._load_project_configuration_view(project_id)
        return ProjectConfigurationDto.from_record(configuration.to_record()).to_dict()

    async def upsert_project_integration(self, project_id: str, current_user_id: str, data: dict):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        provider = (data.get("provider") or "").strip()
        if not provider:
            raise ValidationError("Integration provider is required")
        status = data.get("status") or "disabled"
        integration = await self.repo.upsert_project_integration(
            project_id,
            provider=provider,
            status=status,
            config_json=data.get("config_json") or {},
            credentials_encrypted=data.get("credentials_encrypted"),
        )
        return ProjectIntegrationDto.from_record(integration).to_dict()

    async def upsert_project_channel(self, project_id: str, current_user_id: str, data: dict):
        await self.access_service.require_project_role(project_id, current_user_id, PROJECT_WRITE_ROLES)
        kind = (data.get("kind") or "").strip()
        provider = (data.get("provider") or "").strip()
        if kind not in ALLOWED_CHANNEL_KINDS:
            raise ValidationError("Invalid channel kind")
        if not provider:
            raise ValidationError("Channel provider is required")
        status = data.get("status") or "disabled"
        channel = await self.repo.upsert_project_channel(
            project_id,
            kind=kind,
            provider=provider,
            status=status,
            config_json=data.get("config_json") or {},
        )
        return ProjectChannelDto.from_record(channel).to_dict()
