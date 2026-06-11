from pathlib import Path
from typing import cast

import pytest

from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionDecision,
    SourceIngestionAdmissionPolicy,
    SourceIngestionAdmissionStatus,
)


class FakeProjectAccess:
    def __init__(self, *, project_exists: bool = True, role: str | None = None) -> None:
        self._project_exists = project_exists
        self._role = role
        self.project_exists_calls: list[str] = []
        self.role_lookup_calls: list[tuple[str, str]] = []

    async def project_exists(self, project_id: str) -> bool:
        self.project_exists_calls.append(project_id)
        return self._project_exists

    async def actor_project_role(
        self,
        *,
        project_id: str,
        actor_user_id: str,
    ) -> str | None:
        self.role_lookup_calls.append((project_id, actor_user_id))
        return self._role


@pytest.mark.asyncio
async def test_anonymous_actor_is_denied_before_project_and_role_checks() -> None:
    project_access = FakeProjectAccess(project_exists=True, role="owner")
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-1",
        actor=SourceIngestionActor(actor_user_id=None),
    )

    assert decision.status is SourceIngestionAdmissionStatus.ACTOR_NOT_AUTHENTICATED
    assert decision.reason == "actor_not_authenticated"
    assert decision.is_allowed() is False
    assert project_access.project_exists_calls == []
    assert project_access.role_lookup_calls == []


@pytest.mark.asyncio
async def test_missing_project_is_denied_without_role_lookup() -> None:
    project_access = FakeProjectAccess(project_exists=False, role="owner")
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-missing",
        actor=SourceIngestionActor(actor_user_id="user-1"),
    )

    assert decision.status is SourceIngestionAdmissionStatus.PROJECT_NOT_FOUND
    assert decision.reason == "project_not_found"
    assert decision.is_allowed() is False
    assert project_access.project_exists_calls == ["project-missing"]
    assert project_access.role_lookup_calls == []


@pytest.mark.asyncio
async def test_platform_admin_is_allowed_without_role_lookup() -> None:
    project_access = FakeProjectAccess(project_exists=True, role="manager")
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-1",
        actor=SourceIngestionActor(
            actor_user_id="platform-admin-1",
            is_platform_admin=True,
        ),
    )

    assert decision.status is SourceIngestionAdmissionStatus.ALLOWED
    assert decision.reason == "platform_admin_allowed"
    assert decision.is_allowed() is True
    assert project_access.project_exists_calls == ["project-1"]
    assert project_access.role_lookup_calls == []


@pytest.mark.asyncio
async def test_platform_admin_still_requires_authenticated_actor_id() -> None:
    project_access = FakeProjectAccess(project_exists=True, role="owner")
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-1",
        actor=SourceIngestionActor(
            actor_user_id=None,
            is_platform_admin=True,
        ),
    )

    assert decision.status is SourceIngestionAdmissionStatus.ACTOR_NOT_AUTHENTICATED
    assert decision.reason == "actor_not_authenticated"
    assert decision.is_allowed() is False
    assert project_access.project_exists_calls == []
    assert project_access.role_lookup_calls == []


@pytest.mark.asyncio
async def test_project_owner_is_allowed() -> None:
    project_access = FakeProjectAccess(project_exists=True, role="owner")
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-1",
        actor=SourceIngestionActor(actor_user_id="owner-1"),
    )

    assert decision.status is SourceIngestionAdmissionStatus.ALLOWED
    assert decision.reason == "project_role_allowed"
    assert decision.is_allowed() is True
    assert project_access.role_lookup_calls == [("project-1", "owner-1")]


@pytest.mark.asyncio
async def test_project_admin_is_allowed() -> None:
    project_access = FakeProjectAccess(project_exists=True, role="admin")
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-1",
        actor=SourceIngestionActor(actor_user_id="admin-1"),
    )

    assert decision.status is SourceIngestionAdmissionStatus.ALLOWED
    assert decision.reason == "project_role_allowed"
    assert decision.is_allowed() is True
    assert project_access.role_lookup_calls == [("project-1", "admin-1")]


@pytest.mark.asyncio
async def test_manager_is_denied() -> None:
    project_access = FakeProjectAccess(project_exists=True, role="manager")
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-1",
        actor=SourceIngestionActor(actor_user_id="manager-1"),
    )

    assert decision.status is SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED
    assert decision.reason == "actor_role_not_allowed"
    assert decision.is_allowed() is False
    assert project_access.role_lookup_calls == [("project-1", "manager-1")]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "viewer", "support", "unknown", ""])
async def test_ordinary_or_unknown_role_is_denied(role: str) -> None:
    project_access = FakeProjectAccess(project_exists=True, role=role)
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-1",
        actor=SourceIngestionActor(actor_user_id="user-1"),
    )

    assert decision.status is SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED
    assert decision.reason == "actor_role_not_allowed"
    assert decision.is_allowed() is False
    assert project_access.role_lookup_calls == [("project-1", "user-1")]


@pytest.mark.asyncio
async def test_non_member_is_denied() -> None:
    project_access = FakeProjectAccess(project_exists=True, role=None)
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    decision = await policy.decide(
        project_id="project-1",
        actor=SourceIngestionActor(actor_user_id="user-1"),
    )

    assert decision.status is SourceIngestionAdmissionStatus.ACTOR_NOT_PROJECT_MEMBER
    assert decision.reason == "actor_not_project_member"
    assert decision.is_allowed() is False
    assert project_access.role_lookup_calls == [("project-1", "user-1")]


@pytest.mark.asyncio
async def test_policy_rejects_empty_project_id() -> None:
    project_access = FakeProjectAccess(project_exists=True, role="owner")
    policy = SourceIngestionAdmissionPolicy(project_access=project_access)

    with pytest.raises(ValueError, match="project_id must be non-empty"):
        await policy.decide(
            project_id=" ",
            actor=SourceIngestionActor(actor_user_id="user-1"),
        )


def test_validation_catches_empty_actor_ids() -> None:
    with pytest.raises(ValueError, match="actor_user_id must be non-empty"):
        SourceIngestionActor(actor_user_id="")

    with pytest.raises(ValueError, match="actor_user_id must be non-empty"):
        SourceIngestionActor(actor_user_id="   ")


def test_validation_catches_non_bool_platform_admin_flag() -> None:
    with pytest.raises(TypeError, match="is_platform_admin must be bool"):
        SourceIngestionActor(
            actor_user_id="user-1",
            is_platform_admin=cast(bool, "yes"),
        )


def test_decision_validation_catches_empty_ids_and_reason() -> None:
    with pytest.raises(ValueError, match="project_id must be non-empty"):
        SourceIngestionAdmissionDecision(
            project_id="",
            actor_user_id="user-1",
            status=SourceIngestionAdmissionStatus.PROJECT_NOT_FOUND,
            reason="project_not_found",
        )

    with pytest.raises(ValueError, match="actor_user_id must be non-empty"):
        SourceIngestionAdmissionDecision(
            project_id="project-1",
            actor_user_id="",
            status=SourceIngestionAdmissionStatus.PROJECT_NOT_FOUND,
            reason="project_not_found",
        )

    with pytest.raises(ValueError, match="reason must be non-empty"):
        SourceIngestionAdmissionDecision(
            project_id="project-1",
            actor_user_id="user-1",
            status=SourceIngestionAdmissionStatus.PROJECT_NOT_FOUND,
            reason="",
        )

    with pytest.raises(ValueError, match="actor_user_id must be non-empty"):
        SourceIngestionAdmissionDecision(
            project_id="project-1",
            actor_user_id=None,
            status=SourceIngestionAdmissionStatus.ALLOWED,
            reason="project_role_allowed",
        )


def test_source_ingestion_admission_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/source_ingestion_admission.py"
    ).read_text(encoding="utf-8")

    required_markers = [
        "SourceIngestionAdmissionPolicy",
        "SourceIngestionProjectAccessPort",
        "SourceIngestionActor",
        "SourceIngestionAdmissionDecision",
        "SourceIngestionAdmissionStatus",
        "owner",
        "admin",
        "manager",
        "actor_not_authenticated",
        "project_role_allowed",
    ]
    forbidden_markers = [
        "fastapi",
        "HTTPException",
        "Depends",
        "Header",
        "Request",
        "src.interfaces",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "Postgres",
        "UserRepository",
        "ProjectRepository",
        "get_current_user_id",
        "RunClaimExtractionStageAsync",
        "CLAIM_BUILDER_WORK_SCHEDULED",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
