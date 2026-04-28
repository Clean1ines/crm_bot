from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from src.domain.control_plane.project_configuration import (
    ProjectChannelView,
    ProjectConfigurationView,
    ProjectIntegrationView,
)
from src.domain.control_plane.project_views import (
    ManagerMembershipMutationView,
    ProjectMemberView,
    ProjectSummaryView,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.manager_notifications import ManagerNotificationTarget


class ProjectExistencePort(Protocol):
    async def project_exists(self, project_id: str) -> bool: ...


class ProjectTokenPort(Protocol):
    async def get_webhook_secret(self, project_id: str) -> str | None: ...

    async def get_bot_token(self, project_id: str) -> str | None: ...

    async def get_manager_webhook_secret(self, project_id: str) -> str | None: ...

    async def get_manager_bot_token(self, project_id: str) -> str | None: ...

    async def find_project_by_manager_webhook_secret(
        self, secret_token: str
    ) -> str | None: ...


class ProjectMemberResolverPort(Protocol):
    async def get_manager_notification_targets(self, project_id: str) -> list[str]: ...

    async def resolve_manager_user_id_by_telegram(
        self,
        project_id: str,
        telegram_id: int,
    ) -> str | None: ...


class ProjectNotificationPort(Protocol):
    async def get_project_settings(self, project_id: str) -> JsonObject | None: ...

    async def get_manager_notification_recipients(
        self,
        project_id: str,
    ) -> list[ManagerNotificationTarget]: ...


class ProjectReadPort(Protocol):
    async def get_project_view(self, project_id: str) -> ProjectSummaryView | None: ...

    async def get_projects_for_user_view(
        self, user_id: str
    ) -> list[ProjectSummaryView]: ...

    async def get_project_members_view(
        self, project_id: str
    ) -> list[ProjectMemberView]: ...

    async def get_project_configuration_view(
        self, project_id: str
    ) -> ProjectConfigurationView: ...

    async def get_manager_notification_targets(self, project_id: str) -> list[str]: ...


class ProjectAccessPort(Protocol):
    async def require_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: Collection[str],
    ) -> None: ...


class ProjectControlPort(ProjectReadPort, Protocol):
    async def get_projects_for_owner(
        self, user_id: str
    ) -> list[ProjectSummaryView]: ...

    async def get_project_by_id(self, project_id: str) -> ProjectSummaryView | None: ...

    async def get_project_view(self, project_id: str) -> ProjectSummaryView | None: ...

    async def get_project_member_role(
        self,
        project_id: str,
        user_id: str,
    ) -> str | None: ...

    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: Collection[str],
    ) -> bool: ...

    async def project_exists(self, project_id: str) -> bool: ...

    async def create_project_with_user_id(self, user_id: str, name: str) -> str: ...

    async def update_project(self, project_id: str, name: str | None) -> None: ...

    async def delete_project(self, project_id: str) -> None: ...

    async def set_bot_token(self, project_id: str, token: str | None) -> None: ...

    async def set_manager_bot_token(
        self, project_id: str, token: str | None
    ) -> None: ...

    async def clear_bot_token(self, project_id: str) -> None: ...

    async def clear_manager_token(self, project_id: str) -> None: ...

    async def set_webhook_secret(self, project_id: str, secret_token: str) -> None: ...

    async def set_manager_webhook_secret(
        self, project_id: str, secret_token: str
    ) -> None: ...

    async def add_manager_notification_target(
        self, project_id: str, chat_id: str
    ) -> None: ...

    async def remove_manager_notification_target(
        self, project_id: str, chat_id: str
    ) -> None: ...

    async def add_project_member(
        self, project_id: str, user_id: str, role: str
    ) -> None: ...

    async def remove_project_member(self, project_id: str, user_id: str) -> None: ...

    async def add_manager_by_telegram_identity(
        self, project_id: str, manager_chat_id: str
    ) -> ManagerMembershipMutationView: ...

    async def remove_manager_by_telegram_identity(
        self, project_id: str, manager_chat_id: str
    ) -> None: ...

    async def get_project_settings(self, project_id: str) -> JsonObject | None: ...

    async def update_project_settings(
        self, project_id: str, data: JsonObject
    ) -> None: ...

    async def update_project_policies(
        self, project_id: str, data: JsonObject
    ) -> None: ...

    async def update_project_limit_profile(
        self, project_id: str, data: JsonObject
    ) -> None: ...

    async def upsert_project_integration(
        self,
        project_id: str,
        *,
        provider: str,
        status: str,
        config_json: JsonObject,
        credentials_encrypted: str | None = None,
    ) -> ProjectIntegrationView: ...

    async def upsert_project_channel(
        self,
        project_id: str,
        *,
        kind: str,
        provider: str,
        status: str,
        config_json: JsonObject,
    ) -> ProjectChannelView: ...
