from dataclasses import dataclass, field
from typing import Callable, TypeVar

from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


ViewT = TypeVar("ViewT")


@dataclass(slots=True)
class ProjectIntegrationView:
    provider: str
    id: str | None = None
    project_id: str | None = None
    status: str | None = None
    config_json: JsonObject = field(default_factory=dict)
    credentials_encrypted: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectIntegrationView":
        return cls(
            id=str(record["id"]) if record.get("id") is not None else None,
            project_id=str(record["project_id"]) if record.get("project_id") is not None else None,
            provider=str(record.get("provider") or ""),
            status=_optional_text(record.get("status")),
            config_json=json_object_from_unknown(record.get("config_json")),
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
            "config_json": dict(self.config_json),
            "credentials_encrypted": self.credentials_encrypted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectChannelView:
    kind: str
    provider: str
    id: str | None = None
    project_id: str | None = None
    status: str | None = None
    config_json: JsonObject = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectChannelView":
        return cls(
            id=str(record["id"]) if record.get("id") is not None else None,
            project_id=str(record["project_id"]) if record.get("project_id") is not None else None,
            kind=str(record.get("kind") or ""),
            provider=str(record.get("provider") or ""),
            status=_optional_text(record.get("status")),
            config_json=json_object_from_unknown(record.get("config_json")),
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
            "config_json": dict(self.config_json),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectPromptVersionView:
    id: str | None = None
    name: str | None = None
    version: int | None = None
    prompt_bundle: JsonObject = field(default_factory=dict)
    is_active: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectPromptVersionView":
        version = record.get("version")
        prompt_bundle = record.get("prompt_bundle")
        if prompt_bundle is None:
            prompt_bundle = record.get("prompt_json")

        return cls(
            id=str(record["id"]) if record.get("id") is not None else None,
            name=str(record["name"]) if record.get("name") is not None else None,
            version=int(version) if version is not None else None,
            prompt_bundle=json_object_from_unknown(prompt_bundle),
            is_active=_optional_bool(record.get("is_active")),
            created_at=_optional_text(record.get("created_at")),
            updated_at=_optional_text(record.get("updated_at")),
        )

    def to_record(self) -> dict[str, object]:
        payload = {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "prompt_bundle": dict(self.prompt_bundle),
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectConfigurationView:
    project_id: str
    settings: JsonObject = field(default_factory=dict)
    policies: JsonObject = field(default_factory=dict)
    limit_profile: JsonObject = field(default_factory=dict)
    integrations: list[ProjectIntegrationView] = field(default_factory=list)
    channels: list[ProjectChannelView] = field(default_factory=list)
    prompt_versions: list[ProjectPromptVersionView] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectConfigurationView":
        return cls(
            project_id=str(record.get("project_id") or ""),
            settings=json_object_from_unknown(record.get("settings")),
            policies=json_object_from_unknown(record.get("policies")),
            limit_profile=json_object_from_unknown(record.get("limit_profile")),
            integrations=_view_list(
                record.get("integrations"),
                ProjectIntegrationView,
                ProjectIntegrationView.from_record,
            ),
            channels=_view_list(
                record.get("channels"),
                ProjectChannelView,
                ProjectChannelView.from_record,
            ),
            prompt_versions=_view_list(
                record.get("prompt_versions"),
                ProjectPromptVersionView,
                ProjectPromptVersionView.from_record,
            ),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "settings": dict(self.settings),
            "policies": dict(self.policies),
            "limit_profile": dict(self.limit_profile),
            "integrations": [item.to_record() for item in self.integrations],
            "channels": [item.to_record() for item in self.channels],
            "prompt_versions": [item.to_record() for item in self.prompt_versions],
        }

    def to_runtime_record(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "settings": dict(self.settings),
            "policies": dict(self.policies),
            "limits": dict(self.limit_profile),
            "integrations": [item.to_record() for item in self.integrations],
            "channels": [item.to_record() for item in self.channels],
        }


def _view_list(
    value: object,
    view_type: type[ViewT],
    from_record: Callable[[dict[str, object]], ViewT],
) -> list[ViewT]:
    if not isinstance(value, list):
        return []

    result: list[ViewT] = []
    for item in value:
        parsed = _view_item(item, view_type, from_record)
        if parsed is not None:
            result.append(parsed)
    return result


def _view_item(
    item: object,
    view_type: type[ViewT],
    from_record: Callable[[dict[str, object]], ViewT],
) -> ViewT | None:
    if isinstance(item, view_type):
        return item

    if isinstance(item, dict):
        return from_record(item)

    return None


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value

    return None
