from dataclasses import dataclass, field
from datetime import datetime

from src.domain.display_names import build_display_name
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


def _json_object(value: object) -> JsonObject:
    return json_object_from_unknown(value)


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        try:
            return int(normalized)
        except ValueError:
            return None
    return None


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return None


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
    def from_record(cls, record: dict[str, object]) -> "ProjectSummaryView":
        return cls(
            id=str(record["id"]),
            name=str(record["name"]),
            is_pro_mode=bool(record.get("is_pro_mode")),
            user_id=str(record["user_id"])
            if record.get("user_id") is not None
            else None,
            client_bot_username=_optional_text(record.get("client_bot_username")),
            manager_bot_username=_optional_text(record.get("manager_bot_username")),
            access_role=_optional_text(record.get("access_role")),
            created_at=_optional_datetime(record.get("created_at")),
            updated_at=_optional_datetime(record.get("updated_at")),
        )

    def to_record(self) -> dict[str, object]:
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
    display_name: str | None = None
    email: str | None = None
    project_id: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectMemberView":
        return cls(
            user_id=str(record["user_id"]),
            role=str(record["role"]),
            telegram_id=_optional_int(record.get("telegram_id")),
            username=_optional_text(record.get("username")),
            full_name=_optional_text(record.get("full_name")),
            display_name=_optional_text(record.get("display_name")),
            email=_optional_text(record.get("email")),
            project_id=str(record["project_id"])
            if record.get("project_id") is not None
            else None,
            created_at=_optional_datetime(record.get("created_at")),
        )

    def __post_init__(self) -> None:
        self.display_name = self.display_name or build_display_name(
            full_name=self.full_name,
            username=self.username,
            email=self.email,
            fallback="Менеджер",
        )

    def to_record(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "role": self.role,
            "telegram_id": self.telegram_id,
            "username": self.username,
            "full_name": self.full_name,
            "display_name": self.display_name,
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
        record: dict[str, object] | None,
        *,
        manager_targets: list[str] | None = None,
    ) -> "ProjectRuntimeSettingsView":
        payload = record or {}
        targets = list(manager_targets or [])
        return cls(
            system_prompt=_optional_text(payload.get("system_prompt")),
            bot_token=_optional_text(payload.get("bot_token")),
            webhook_url=_optional_text(payload.get("webhook_url")),
            manager_bot_token=_optional_text(payload.get("manager_bot_token")),
            webhook_secret=_optional_text(payload.get("webhook_secret")),
            is_pro_mode=bool(payload.get("is_pro_mode")),
            client_bot_username=_optional_text(payload.get("client_bot_username")),
            manager_bot_username=_optional_text(payload.get("manager_bot_username")),
            manager_notification_targets=targets,
            manager_chat_ids=targets.copy(),
        )

    def to_record(self) -> dict[str, object]:
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
    config_json: JsonObject = field(default_factory=dict)
    credentials_encrypted: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectIntegrationView":
        return cls(
            id=str(record["id"]),
            project_id=str(record["project_id"]),
            provider=str(record["provider"]),
            status=_optional_text(record.get("status")),
            config_json=_json_object(record.get("config_json")),
            credentials_encrypted=_optional_text(record.get("credentials_encrypted")),
            created_at=_optional_text(record.get("created_at")),
            updated_at=_optional_text(record.get("updated_at")),
        )

    def to_record(self) -> dict[str, object]:
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
    config_json: JsonObject = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectChannelView":
        return cls(
            id=str(record["id"]),
            project_id=str(record["project_id"]),
            kind=str(record["kind"]),
            provider=str(record["provider"]),
            status=_optional_text(record.get("status")),
            config_json=_json_object(record.get("config_json")),
            created_at=_optional_text(record.get("created_at")),
            updated_at=_optional_text(record.get("updated_at")),
        )

    def to_record(self) -> dict[str, object]:
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

    def to_record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "storage": self.storage,
            "user_id": self.user_id,
            "role": self.role,
        }
