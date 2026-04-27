from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


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
            credentials_encrypted=str(credentials_encrypted) if credentials_encrypted is not None else None,
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
            version=int(version) if version is not None else None,
            prompt_bundle=_as_dict(record.get("prompt_bundle")),
            is_active=bool(is_active) if is_active is not None else None,
            created_at=str(created_at) if created_at is not None else None,
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
            client_bot_username=str(client_bot_username) if client_bot_username is not None else None,
            manager_bot_username=str(manager_bot_username) if manager_bot_username is not None else None,
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
        integrations: list[ProjectIntegrationDto] = []
        for item in _as_list(record.get("integrations")):
            if isinstance(item, ProjectIntegrationDto):
                integrations.append(item)
            elif isinstance(item, Mapping):
                integrations.append(ProjectIntegrationDto.from_record(item))

        channels: list[ProjectChannelDto] = []
        for item in _as_list(record.get("channels")):
            if isinstance(item, ProjectChannelDto):
                channels.append(item)
            elif isinstance(item, Mapping):
                channels.append(ProjectChannelDto.from_record(item))

        prompt_versions: list[ProjectPromptVersionDto] = []
        for item in _as_list(record.get("prompt_versions")):
            if isinstance(item, ProjectPromptVersionDto):
                prompt_versions.append(item)
            elif isinstance(item, Mapping):
                prompt_versions.append(ProjectPromptVersionDto.from_record(item))

        return cls(
            project_id=str(record.get("project_id") or ""),
            settings=_as_dict(record.get("settings")),
            policies=_as_dict(record.get("policies")),
            limit_profile=_as_dict(record.get("limit_profile")),
            integrations=integrations,
            channels=channels,
            prompt_versions=prompt_versions,
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
            id=int(record["id"]),
            thread_id=str(record["thread_id"]),
            project_id=str(record["project_id"]),
            manager_user_id=str(record["manager_user_id"]),
            manager_chat_id=str(manager_chat_id) if manager_chat_id is not None else None,
            text=str(record.get("text") or ""),
            created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at) if created_at else None,
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
            items=[ManagerReplyHistoryItemDto.from_record(record) for record in records],
            limit=limit,
            offset=offset,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "limit": self.limit,
            "offset": self.offset,
        }
