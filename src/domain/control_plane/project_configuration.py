from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProjectIntegrationView:
    provider: str
    status: str | None = None
    config_json: dict[str, Any] = field(default_factory=dict)
    credentials_encrypted: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectIntegrationView":
        return cls(
            provider=str(record.get("provider") or ""),
            status=record.get("status"),
            config_json=dict(record.get("config_json") or {}),
            credentials_encrypted=record.get("credentials_encrypted"),
        )

    def to_record(self) -> dict[str, Any]:
        payload = {
            "provider": self.provider,
            "status": self.status,
            "config_json": dict(self.config_json),
            "credentials_encrypted": self.credentials_encrypted,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectChannelView:
    kind: str
    provider: str
    status: str | None = None
    config_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectChannelView":
        return cls(
            kind=str(record.get("kind") or ""),
            provider=str(record.get("provider") or ""),
            status=record.get("status"),
            config_json=dict(record.get("config_json") or {}),
        )

    def to_record(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "provider": self.provider,
            "status": self.status,
            "config_json": dict(self.config_json),
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectPromptVersionView:
    version: int | None = None
    prompt_bundle: dict[str, Any] = field(default_factory=dict)
    is_active: bool | None = None
    created_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectPromptVersionView":
        version = record.get("version")
        return cls(
            version=int(version) if version is not None else None,
            prompt_bundle=dict(record.get("prompt_bundle") or {}),
            is_active=record.get("is_active"),
            created_at=record.get("created_at"),
        )

    def to_record(self) -> dict[str, Any]:
        payload = {
            "version": self.version,
            "prompt_bundle": dict(self.prompt_bundle),
            "is_active": self.is_active,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectConfigurationView:
    project_id: str
    settings: dict[str, Any] = field(default_factory=dict)
    policies: dict[str, Any] = field(default_factory=dict)
    limit_profile: dict[str, Any] = field(default_factory=dict)
    integrations: list[ProjectIntegrationView] = field(default_factory=list)
    channels: list[ProjectChannelView] = field(default_factory=list)
    prompt_versions: list[ProjectPromptVersionView] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectConfigurationView":
        return cls(
            project_id=str(record.get("project_id") or ""),
            settings=dict(record.get("settings") or {}),
            policies=dict(record.get("policies") or {}),
            limit_profile=dict(record.get("limit_profile") or {}),
            integrations=[
                item if isinstance(item, ProjectIntegrationView) else ProjectIntegrationView.from_record(item)
                for item in (record.get("integrations") or [])
                if isinstance(item, (dict, ProjectIntegrationView))
            ],
            channels=[
                item if isinstance(item, ProjectChannelView) else ProjectChannelView.from_record(item)
                for item in (record.get("channels") or [])
                if isinstance(item, (dict, ProjectChannelView))
            ],
            prompt_versions=[
                item if isinstance(item, ProjectPromptVersionView) else ProjectPromptVersionView.from_record(item)
                for item in (record.get("prompt_versions") or [])
                if isinstance(item, (dict, ProjectPromptVersionView))
            ],
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "settings": dict(self.settings),
            "policies": dict(self.policies),
            "limit_profile": dict(self.limit_profile),
            "integrations": [item.to_record() for item in self.integrations],
            "channels": [item.to_record() for item in self.channels],
            "prompt_versions": [item.to_record() for item in self.prompt_versions],
        }

    def to_runtime_record(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "settings": dict(self.settings),
            "policies": dict(self.policies),
            "limits": dict(self.limit_profile),
            "integrations": [item.to_record() for item in self.integrations],
            "channels": [item.to_record() for item in self.channels],
        }
