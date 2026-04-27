from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from typing import TypeVar

from src.domain.control_plane.project_configuration import (
    ProjectChannelView,
    ProjectConfigurationView,
    ProjectIntegrationView,
    ProjectPromptVersionView,
)
from src.domain.control_plane.project_views import ProjectSummaryView
from src.domain.project_plane.manager_reply_history import ManagerReplyHistoryItemView


DtoT = TypeVar("DtoT")


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default


def _serialize_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _dto_list(
    raw_items: object,
    dto_type: type[DtoT],
    from_record: Callable[[Mapping[str, object]], DtoT],
) -> list[DtoT]:
    result: list[DtoT] = []
    for item in _as_list(raw_items):
        parsed = _dto_item(item, dto_type, from_record)
        if parsed is not None:
            result.append(parsed)
    return result


def _dto_item(
    item: object,
    dto_type: type[DtoT],
    from_record: Callable[[Mapping[str, object]], DtoT],
) -> DtoT | None:
    if isinstance(item, dto_type):
        return item
    if isinstance(item, Mapping):
        return from_record(item)
    return None


@dataclass(frozen=True, slots=True)
class ProjectIntegrationDto:
    provider: str
    status: str | None = None
    config_json: dict[str, object] = field(default_factory=dict)
    credentials_encrypted: str | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "ProjectIntegrationDto":
        status = record.get("status")
        credentials_encrypted = record.get("credentials_encrypted")

        return cls(
            provider=str(record.get("provider") or ""),
            status=str(status) if status is not None else None,
            config_json=_as_dict(record.get("config_json")),
            credentials_encrypted=str(credentials_encrypted)
            if credentials_encrypted is not None
            else None,
        )

    @classmethod
    def from_view(cls, view: ProjectIntegrationView) -> "ProjectIntegrationDto":
        return cls(
            provider=view.provider,
            status=view.status,
            config_json=dict(view.config_json),
            credentials_encrypted=view.credentials_encrypted,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if not payload.get("config_json"):
            payload.pop("config_json", None)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True, slots=True)
class ProjectChannelDto:
    kind: str
    provider: str
    status: str | None = None
    config_json: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "ProjectChannelDto":
        status = record.get("status")

        return cls(
            kind=str(record.get("kind") or ""),
            provider=str(record.get("provider") or ""),
            status=str(status) if status is not None else None,
            config_json=_as_dict(record.get("config_json")),
        )

    @classmethod
    def from_view(cls, view: ProjectChannelView) -> "ProjectChannelDto":
        return cls(
            kind=view.kind,
            provider=view.provider,
            status=view.status,
            config_json=dict(view.config_json),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if not payload.get("config_json"):
            payload.pop("config_json", None)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True, slots=True)
class ProjectPromptVersionDto:
    version: int | None = None
    prompt_bundle: dict[str, object] = field(default_factory=dict)
    is_active: bool | None = None
    created_at: str | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "ProjectPromptVersionDto":
        version = record.get("version")
        is_active = record.get("is_active")
        created_at = record.get("created_at")

        return cls(
            version=_coerce_int(version) if version is not None else None,
            prompt_bundle=_as_dict(record.get("prompt_bundle")),
            is_active=bool(is_active) if is_active is not None else None,
            created_at=str(created_at) if created_at is not None else None,
        )

    @classmethod
    def from_view(cls, view: ProjectPromptVersionView) -> "ProjectPromptVersionDto":
        return cls(
            version=view.version,
            prompt_bundle=dict(view.prompt_bundle),
            is_active=view.is_active,
            created_at=_serialize_timestamp(view.created_at),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if not payload.get("prompt_bundle"):
            payload.pop("prompt_bundle", None)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True, slots=True)
class ProjectSummaryDto:
    id: str
    name: str
    is_pro_mode: bool
    user_id: str | None
    client_bot_username: str | None = None
    manager_bot_username: str | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "ProjectSummaryDto":
        user_id = record.get("user_id")
        client_bot_username = record.get("client_bot_username")
        manager_bot_username = record.get("manager_bot_username")

        return cls(
            id=str(record["id"]),
            name=str(record["name"]),
            is_pro_mode=bool(record.get("is_pro_mode")),
            user_id=str(user_id) if user_id is not None else None,
            client_bot_username=str(client_bot_username)
            if client_bot_username is not None
            else None,
            manager_bot_username=str(manager_bot_username)
            if manager_bot_username is not None
            else None,
        )

    @classmethod
    def from_view(cls, view: ProjectSummaryView) -> "ProjectSummaryDto":
        return cls(
            id=view.id,
            name=view.name,
            is_pro_mode=view.is_pro_mode,
            user_id=view.user_id,
            client_bot_username=view.client_bot_username,
            manager_bot_username=view.manager_bot_username,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProjectConfigurationDto:
    project_id: str
    settings: dict[str, object] = field(default_factory=dict)
    policies: dict[str, object] = field(default_factory=dict)
    limit_profile: dict[str, object] = field(default_factory=dict)
    integrations: list[ProjectIntegrationDto] = field(default_factory=list)
    channels: list[ProjectChannelDto] = field(default_factory=list)
    prompt_versions: list[ProjectPromptVersionDto] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "ProjectConfigurationDto":
        return cls(
            project_id=str(record.get("project_id") or ""),
            settings=_as_dict(record.get("settings")),
            policies=_as_dict(record.get("policies")),
            limit_profile=_as_dict(record.get("limit_profile")),
            integrations=_dto_list(
                record.get("integrations"),
                ProjectIntegrationDto,
                ProjectIntegrationDto.from_record,
            ),
            channels=_dto_list(
                record.get("channels"),
                ProjectChannelDto,
                ProjectChannelDto.from_record,
            ),
            prompt_versions=_dto_list(
                record.get("prompt_versions"),
                ProjectPromptVersionDto,
                ProjectPromptVersionDto.from_record,
            ),
        )

    @classmethod
    def from_view(cls, view: ProjectConfigurationView) -> "ProjectConfigurationDto":
        return cls(
            project_id=view.project_id,
            settings=dict(view.settings),
            policies=dict(view.policies),
            limit_profile=dict(view.limit_profile),
            integrations=[
                ProjectIntegrationDto.from_view(item) for item in view.integrations
            ],
            channels=[ProjectChannelDto.from_view(item) for item in view.channels],
            prompt_versions=[
                ProjectPromptVersionDto.from_view(item) for item in view.prompt_versions
            ],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "settings": dict(self.settings),
            "policies": dict(self.policies),
            "limit_profile": dict(self.limit_profile),
            "integrations": [item.to_dict() for item in self.integrations],
            "channels": [item.to_dict() for item in self.channels],
            "prompt_versions": [item.to_dict() for item in self.prompt_versions],
        }


@dataclass(frozen=True, slots=True)
class ManagerReplyHistoryItemDto:
    id: int
    thread_id: str
    project_id: str
    manager_user_id: str
    text: str
    manager_chat_id: str | None = None
    created_at: str | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "ManagerReplyHistoryItemDto":
        created_at = record.get("created_at")
        manager_chat_id = record.get("manager_chat_id")

        return cls(
            id=_coerce_int(record["id"]),
            thread_id=str(record["thread_id"]),
            project_id=str(record["project_id"]),
            manager_user_id=str(record["manager_user_id"]),
            manager_chat_id=str(manager_chat_id)
            if manager_chat_id is not None
            else None,
            text=str(record.get("text") or ""),
            created_at=_serialize_timestamp(created_at),
        )

    @classmethod
    def from_view(
        cls, view: ManagerReplyHistoryItemView
    ) -> "ManagerReplyHistoryItemDto":
        return cls(
            id=view.id,
            thread_id=view.thread_id,
            project_id=view.project_id,
            manager_user_id=view.manager_user_id,
            manager_chat_id=view.manager_chat_id,
            text=view.text,
            created_at=_serialize_timestamp(view.created_at),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True, slots=True)
class ManagerReplyHistoryDto:
    items: list[ManagerReplyHistoryItemDto]
    limit: int
    offset: int

    @classmethod
    def from_records(
        cls,
        records: list[dict[str, object]],
        *,
        limit: int,
        offset: int,
    ) -> "ManagerReplyHistoryDto":
        return cls(
            items=[
                ManagerReplyHistoryItemDto.from_record(record) for record in records
            ],
            limit=limit,
            offset=offset,
        )

    @classmethod
    def from_views(
        cls,
        views: list[ManagerReplyHistoryItemView],
        *,
        limit: int,
        offset: int,
    ) -> "ManagerReplyHistoryDto":
        return cls(
            items=[ManagerReplyHistoryItemDto.from_view(view) for view in views],
            limit=limit,
            offset=offset,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "limit": self.limit,
            "offset": self.offset,
        }
