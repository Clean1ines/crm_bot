from dataclasses import asdict, dataclass

from src.application.dto.project_dto import ProjectSummaryDto
from src.domain.display_names import build_display_name
from src.domain.control_plane.project_views import ProjectMemberView


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.lstrip("-").isdigit():
            return int(normalized)
    return None


def _serialize_timestamp(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


@dataclass(slots=True)
class ProjectMemberDto:
    project_id: str
    user_id: str
    role: str
    id: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    display_name: str | None = None
    email: str | None = None
    created_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectMemberDto":
        full_name = _optional_str(record.get("full_name"))
        username = _optional_str(record.get("username"))
        email = _optional_str(record.get("email"))
        display_name = _optional_str(record.get("display_name")) or build_display_name(
            full_name=full_name,
            username=username,
            email=email,
            fallback="Менеджер",
        )
        return cls(
            id=_optional_str(record.get("id")),
            project_id=str(record["project_id"]),
            user_id=str(record["user_id"]),
            role=str(record["role"]),
            telegram_id=_optional_int(record.get("telegram_id")),
            username=username,
            full_name=full_name,
            display_name=display_name,
            email=email,
            created_at=_serialize_timestamp(record.get("created_at")),
        )

    @classmethod
    def from_view(cls, view: ProjectMemberView) -> "ProjectMemberDto":
        return cls(
            id=_optional_str(getattr(view, "id", None)),
            project_id=str(view.project_id) if view.project_id is not None else "",
            user_id=str(view.user_id),
            role=str(view.role),
            telegram_id=_optional_int(view.telegram_id),
            username=_optional_str(view.username),
            full_name=_optional_str(view.full_name),
            display_name=_optional_str(view.display_name),
            email=_optional_str(view.email),
            created_at=_serialize_timestamp(view.created_at),
        )

    def to_dict(self) -> dict[str, object]:
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
        return cls(
            status=status, type=type, storage=storage, user_id=user_id, role=role
        )

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ProjectMutationResultDto":
        return cls(
            status=str(record["status"]),
            type=_optional_str(record.get("type")),
            storage=_optional_str(record.get("storage")),
            user_id=_optional_str(record.get("user_id")),
            role=_optional_str(record.get("role")),
        )

    def to_dict(self) -> dict[str, object]:
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

    def to_dict(self) -> dict[str, object]:
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

    def to_dict(self) -> dict[str, object]:
        return {"projects": [project.to_dict() for project in self.projects]}
