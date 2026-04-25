from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ProjectIntegrationDto:
    provider: str
    status: Optional[str] = None
    config_json: Dict[str, Any] = field(default_factory=dict)
    credentials_encrypted: Optional[str] = None

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "ProjectIntegrationDto":
        return cls(
            provider=str(record.get("provider") or ""),
            status=record.get("status"),
            config_json=dict(record.get("config_json") or {}),
            credentials_encrypted=record.get("credentials_encrypted"),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if not payload.get("config_json"):
            payload.pop("config_json", None)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class ProjectChannelDto:
    kind: str
    provider: str
    status: Optional[str] = None
    config_json: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "ProjectChannelDto":
        return cls(
            kind=str(record.get("kind") or ""),
            provider=str(record.get("provider") or ""),
            status=record.get("status"),
            config_json=dict(record.get("config_json") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if not payload.get("config_json"):
            payload.pop("config_json", None)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class ProjectPromptVersionDto:
    version: Optional[int] = None
    prompt_bundle: Dict[str, Any] = field(default_factory=dict)
    is_active: Optional[bool] = None
    created_at: Optional[str] = None

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "ProjectPromptVersionDto":
        version = record.get("version")
        return cls(
            version=int(version) if version is not None else None,
            prompt_bundle=dict(record.get("prompt_bundle") or {}),
            is_active=record.get("is_active"),
            created_at=record.get("created_at"),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if not payload.get("prompt_bundle"):
            payload.pop("prompt_bundle", None)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class ProjectSummaryDto:
    id: str
    name: str
    is_pro_mode: bool
    user_id: Optional[str]
    client_bot_username: Optional[str] = None
    manager_bot_username: Optional[str] = None

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "ProjectSummaryDto":
        return cls(
            id=str(record["id"]),
            name=str(record["name"]),
            is_pro_mode=bool(record.get("is_pro_mode")),
            user_id=str(record["user_id"]) if record.get("user_id") is not None else None,
            client_bot_username=record.get("client_bot_username"),
            manager_bot_username=record.get("manager_bot_username"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectConfigurationDto:
    project_id: str
    settings: Dict[str, Any] = field(default_factory=dict)
    policies: Dict[str, Any] = field(default_factory=dict)
    limit_profile: Dict[str, Any] = field(default_factory=dict)
    integrations: List[ProjectIntegrationDto] = field(default_factory=list)
    channels: List[ProjectChannelDto] = field(default_factory=list)
    prompt_versions: List[ProjectPromptVersionDto] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "ProjectConfigurationDto":
        return cls(
            project_id=str(record.get("project_id") or ""),
            settings=dict(record.get("settings") or {}),
            policies=dict(record.get("policies") or {}),
            limit_profile=dict(record.get("limit_profile") or {}),
            integrations=[
                item if isinstance(item, ProjectIntegrationDto) else ProjectIntegrationDto.from_record(item)
                for item in record.get("integrations") or []
                if isinstance(item, (dict, ProjectIntegrationDto))
            ],
            channels=[
                item if isinstance(item, ProjectChannelDto) else ProjectChannelDto.from_record(item)
                for item in record.get("channels") or []
                if isinstance(item, (dict, ProjectChannelDto))
            ],
            prompt_versions=[
                item if isinstance(item, ProjectPromptVersionDto) else ProjectPromptVersionDto.from_record(item)
                for item in record.get("prompt_versions") or []
                if isinstance(item, (dict, ProjectPromptVersionDto))
            ],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "settings": dict(self.settings),
            "policies": dict(self.policies),
            "limit_profile": dict(self.limit_profile),
            "integrations": [item.to_dict() for item in self.integrations],
            "channels": [item.to_dict() for item in self.channels],
            "prompt_versions": [item.to_dict() for item in self.prompt_versions],
        }
