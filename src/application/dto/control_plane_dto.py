from dataclasses import asdict, dataclass
from typing import Any

from src.application.dto.project_dto import ProjectSummaryDto


@dataclass(slots=True)
class ProjectMemberDto:
    project_id: str
    user_id: str
    role: str
    id: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    created_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectMemberDto":
        telegram_id = record.get("telegram_id")
        return cls(
            id=str(record["id"]) if record.get("id") is not None else None,
            project_id=str(record["project_id"]),
            user_id=str(record["user_id"]),
            role=str(record["role"]),
            telegram_id=int(telegram_id) if telegram_id is not None else None,
            username=record.get("username"),
            full_name=record.get("full_name"),
            email=record.get("email"),
            created_at=record.get("created_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectMutationResultDto:
    status: str
    type: str | None = None
    storage: str | None = None
    user_id: str | None = None
    role: str | None = None

    @classmethod
    def create(
        cls,
        *,
        status: str,
        type: str | None = None,
        storage: str | None = None,
        user_id: str | None = None,
        role: str | None = None,
    ) -> "ProjectMutationResultDto":
        return cls(status=status, type=type, storage=storage, user_id=user_id, role=role)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectMutationResultDto":
        return cls(
            status=str(record["status"]),
            type=record.get("type"),
            storage=record.get("storage"),
            user_id=record.get("user_id"),
            role=record.get("role"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ProjectTeamDto:
    members: list[ProjectMemberDto]
    legacy_targets: list[str]

    @classmethod
    def create(
        cls,
        *,
        members: list[ProjectMemberDto],
        legacy_targets: list[str] | None = None,
    ) -> "ProjectTeamDto":
        return cls(members=members, legacy_targets=legacy_targets or [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "members": [member.to_dict() for member in self.members],
            "legacy_targets": self.legacy_targets,
        }


@dataclass(slots=True)
class TelegramAdminProjectsDto:
    projects: list[ProjectSummaryDto]

    @classmethod
    def create(cls, projects: list[ProjectSummaryDto]) -> "TelegramAdminProjectsDto":
        return cls(projects=projects)

    def to_dict(self) -> dict[str, Any]:
        return {"projects": [project.to_dict() for project in self.projects]}
