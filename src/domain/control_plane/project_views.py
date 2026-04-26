from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ProjectSummaryView:
    id: str
    name: str
    is_pro_mode: bool
    user_id: str | None = None
    client_bot_username: str | None = None
    manager_bot_username: str | None = None
    access_role: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectSummaryView":
        return cls(
            id=str(record["id"]),
            name=str(record["name"]),
            is_pro_mode=bool(record.get("is_pro_mode")),
            user_id=str(record["user_id"]) if record.get("user_id") is not None else None,
            client_bot_username=record.get("client_bot_username"),
            manager_bot_username=record.get("manager_bot_username"),
            access_role=record.get("access_role"),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "is_pro_mode": self.is_pro_mode,
            "user_id": self.user_id,
            "client_bot_username": self.client_bot_username,
            "manager_bot_username": self.manager_bot_username,
            "access_role": self.access_role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ProjectMemberView:
    user_id: str
    role: str
    telegram_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    project_id: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectMemberView":
        return cls(
            user_id=str(record["user_id"]),
            role=str(record["role"]),
            telegram_id=record.get("telegram_id"),
            username=record.get("username"),
            full_name=record.get("full_name"),
            email=record.get("email"),
            project_id=str(record["project_id"]) if record.get("project_id") is not None else None,
            created_at=record.get("created_at"),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "role": self.role,
            "telegram_id": self.telegram_id,
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "project_id": self.project_id,
            "created_at": self.created_at,
        }

@dataclass(slots=True)
class ProjectRuntimeSettingsView:
    system_prompt: str | None = None
    bot_token: str | None = None
    webhook_url: str | None = None
    manager_bot_token: str | None = None
    webhook_secret: str | None = None
    is_pro_mode: bool = False
    client_bot_username: str | None = None
    manager_bot_username: str | None = None
    manager_notification_targets: list[str] = field(default_factory=list)
    manager_chat_ids: list[str] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "ProjectRuntimeSettingsView":
        return cls()

    @classmethod
    def from_record(
        cls,
        record: dict[str, Any] | None,
        *,
        manager_targets: list[str] | None = None,
    ) -> "ProjectRuntimeSettingsView":
        payload = record or {}
        targets = list(manager_targets or [])
        return cls(
            system_prompt=payload.get("system_prompt"),
            bot_token=payload.get("bot_token"),
            webhook_url=payload.get("webhook_url"),
            manager_bot_token=payload.get("manager_bot_token"),
            webhook_secret=payload.get("webhook_secret"),
            is_pro_mode=bool(payload.get("is_pro_mode")),
            client_bot_username=payload.get("client_bot_username"),
            manager_bot_username=payload.get("manager_bot_username"),
            manager_notification_targets=targets,
            manager_chat_ids=targets.copy(),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "bot_token": self.bot_token,
            "webhook_url": self.webhook_url,
            "manager_bot_token": self.manager_bot_token,
            "webhook_secret": self.webhook_secret,
            "is_pro_mode": self.is_pro_mode,
            "client_bot_username": self.client_bot_username,
            "manager_bot_username": self.manager_bot_username,
            "manager_notification_targets": self.manager_notification_targets.copy(),
            "manager_chat_ids": self.manager_chat_ids.copy(),
        }


@dataclass(slots=True)
class ProjectIntegrationView:
    id: str
    project_id: str
    provider: str
    status: str | None = None
    config_json: dict[str, Any] = field(default_factory=dict)
    credentials_encrypted: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectIntegrationView":
        return cls(
            id=str(record["id"]),
            project_id=str(record["project_id"]),
            provider=str(record["provider"]),
            status=record.get("status"),
            config_json=dict(record.get("config_json") or {}),
            credentials_encrypted=record.get("credentials_encrypted"),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
        )

    def to_record(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "project_id": self.project_id,
            "provider": self.provider,
            "status": self.status,
            "config_json": self.config_json.copy(),
            "credentials_encrypted": self.credentials_encrypted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectChannelView:
    id: str
    project_id: str
    kind: str
    provider: str
    status: str | None = None
    config_json: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectChannelView":
        return cls(
            id=str(record["id"]),
            project_id=str(record["project_id"]),
            kind=str(record["kind"]),
            provider=str(record["provider"]),
            status=record.get("status"),
            config_json=dict(record.get("config_json") or {}),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
        )

    def to_record(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "project_id": self.project_id,
            "kind": self.kind,
            "provider": self.provider,
            "status": self.status,
            "config_json": self.config_json.copy(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ManagerMembershipMutationView:
    status: str
    storage: str
    user_id: str
    role: str

    def to_record(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "storage": self.storage,
            "user_id": self.user_id,
            "role": self.role,
        }

