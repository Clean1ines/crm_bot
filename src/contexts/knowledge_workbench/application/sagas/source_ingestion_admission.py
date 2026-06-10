from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


_ALLOWED_SOURCE_INGESTION_ROLES = frozenset({"owner", "admin"})
_DENIED_SOURCE_INGESTION_ROLES = frozenset({"manager"})


class SourceIngestionAdmissionStatus(StrEnum):
    ALLOWED = "ALLOWED"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    ACTOR_NOT_AUTHENTICATED = "ACTOR_NOT_AUTHENTICATED"
    ACTOR_NOT_PROJECT_MEMBER = "ACTOR_NOT_PROJECT_MEMBER"
    ACTOR_ROLE_NOT_ALLOWED = "ACTOR_ROLE_NOT_ALLOWED"


@dataclass(frozen=True, slots=True)
class SourceIngestionActor:
    actor_user_id: str | None
    is_platform_admin: bool = False

    def __post_init__(self) -> None:
        if self.actor_user_id is not None:
            _require_non_empty_text(self.actor_user_id, field_name="actor_user_id")
        if not isinstance(self.is_platform_admin, bool):
            raise TypeError("is_platform_admin must be bool")


@dataclass(frozen=True, slots=True)
class SourceIngestionAdmissionDecision:
    project_id: str
    actor_user_id: str | None
    status: SourceIngestionAdmissionStatus
    reason: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(self.reason, field_name="reason")

        if self.actor_user_id is not None:
            _require_non_empty_text(self.actor_user_id, field_name="actor_user_id")

        if not isinstance(self.status, SourceIngestionAdmissionStatus):
            raise TypeError("status must be SourceIngestionAdmissionStatus")

        if (
            self.status is SourceIngestionAdmissionStatus.ALLOWED
            and self.actor_user_id is None
        ):
            raise ValueError("actor_user_id must be non-empty for allowed decision")

    def is_allowed(self) -> bool:
        return self.status is SourceIngestionAdmissionStatus.ALLOWED


class SourceIngestionProjectAccessPort(Protocol):
    async def project_exists(self, project_id: str) -> bool: ...

    async def actor_project_role(
        self,
        *,
        project_id: str,
        actor_user_id: str,
    ) -> str | None: ...


class SourceIngestionAdmissionPolicy:
    def __init__(self, *, project_access: SourceIngestionProjectAccessPort) -> None:
        self._project_access = project_access

    async def decide(
        self,
        *,
        project_id: str,
        actor: SourceIngestionActor,
    ) -> SourceIngestionAdmissionDecision:
        _require_non_empty_text(project_id, field_name="project_id")

        if actor.actor_user_id is None:
            return SourceIngestionAdmissionDecision(
                project_id=project_id,
                actor_user_id=None,
                status=SourceIngestionAdmissionStatus.ACTOR_NOT_AUTHENTICATED,
                reason="actor_not_authenticated",
            )

        if not await self._project_access.project_exists(project_id):
            return SourceIngestionAdmissionDecision(
                project_id=project_id,
                actor_user_id=actor.actor_user_id,
                status=SourceIngestionAdmissionStatus.PROJECT_NOT_FOUND,
                reason="project_not_found",
            )

        if actor.is_platform_admin:
            return SourceIngestionAdmissionDecision(
                project_id=project_id,
                actor_user_id=actor.actor_user_id,
                status=SourceIngestionAdmissionStatus.ALLOWED,
                reason="platform_admin_allowed",
            )

        role = await self._project_access.actor_project_role(
            project_id=project_id,
            actor_user_id=actor.actor_user_id,
        )

        if role is None:
            return SourceIngestionAdmissionDecision(
                project_id=project_id,
                actor_user_id=actor.actor_user_id,
                status=SourceIngestionAdmissionStatus.ACTOR_NOT_PROJECT_MEMBER,
                reason="actor_not_project_member",
            )

        normalized_role = role.strip().lower()
        if (
            normalized_role in _DENIED_SOURCE_INGESTION_ROLES
            or normalized_role not in _ALLOWED_SOURCE_INGESTION_ROLES
        ):
            return SourceIngestionAdmissionDecision(
                project_id=project_id,
                actor_user_id=actor.actor_user_id,
                status=SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED,
                reason="actor_role_not_allowed",
            )

        return SourceIngestionAdmissionDecision(
            project_id=project_id,
            actor_user_id=actor.actor_user_id,
            status=SourceIngestionAdmissionStatus.ALLOWED,
            reason="project_role_allowed",
        )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
