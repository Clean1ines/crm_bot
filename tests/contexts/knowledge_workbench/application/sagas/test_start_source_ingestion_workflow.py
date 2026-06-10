from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionDecision,
    SourceIngestionAdmissionPolicy,
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.application.sagas.start_source_ingestion_workflow import (
    SourceIngestionAcceptedPlan,
    StartSourceIngestionWorkflow,
    StartSourceIngestionWorkflowCommand,
    StartSourceIngestionWorkflowResult,
    StartSourceIngestionWorkflowStatus,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
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


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _command(
    *,
    project_id: str = "project-1",
    actor_user_id: str | None = "user-1",
    source_format: SourceFormat = SourceFormat.MARKDOWN,
    original_filename: str | None = "knowledge.md",
    content_bytes: bytes = b"# Knowledge\n\nHello",
    occurred_at: datetime | None = None,
) -> StartSourceIngestionWorkflowCommand:
    return StartSourceIngestionWorkflowCommand(
        project_id=project_id,
        actor=SourceIngestionActor(actor_user_id=actor_user_id),
        original_filename=original_filename,
        source_format=source_format,
        content_bytes=content_bytes,
        occurred_at=occurred_at or _now(),
    )


def _workflow_for_role(role: str | None) -> StartSourceIngestionWorkflow:
    return StartSourceIngestionWorkflow(
        admission_policy=SourceIngestionAdmissionPolicy(
            project_access=FakeProjectAccess(project_exists=True, role=role),
        ),
    )


def _allowed_admission() -> SourceIngestionAdmissionDecision:
    return SourceIngestionAdmissionDecision(
        project_id="project-1",
        actor_user_id="owner-1",
        status=SourceIngestionAdmissionStatus.ALLOWED,
        reason="project_role_allowed",
    )


def _denied_admission() -> SourceIngestionAdmissionDecision:
    return SourceIngestionAdmissionDecision(
        project_id="project-1",
        actor_user_id="manager-1",
        status=SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED,
        reason="actor_role_not_allowed",
    )


def _accepted_plan() -> SourceIngestionAcceptedPlan:
    return SourceIngestionAcceptedPlan(
        project_id="project-1",
        actor_user_id="owner-1",
        source_document_ref="source-document:project-1:abc",
        source_format=SourceFormat.MARKDOWN,
        content_hash="sha256:abc",
        original_filename="knowledge.md",
        occurred_at=_now(),
    )


@pytest.mark.asyncio
async def test_rejected_anonymous_actor() -> None:
    result = await _workflow_for_role("owner").execute(
        _command(actor_user_id=None),
    )

    assert result.status is StartSourceIngestionWorkflowStatus.REJECTED
    assert result.accepted_plan is None
    assert (
        result.admission.status
        is SourceIngestionAdmissionStatus.ACTOR_NOT_AUTHENTICATED
    )


@pytest.mark.asyncio
async def test_rejected_manager() -> None:
    result = await _workflow_for_role("manager").execute(
        _command(actor_user_id="manager-1"),
    )

    assert result.status is StartSourceIngestionWorkflowStatus.REJECTED
    assert result.accepted_plan is None
    assert (
        result.admission.status is SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED
    )


@pytest.mark.asyncio
async def test_owner_accepted() -> None:
    command = _command(actor_user_id="owner-1")
    result = await _workflow_for_role("owner").execute(command)

    assert result.status is StartSourceIngestionWorkflowStatus.ACCEPTED
    assert result.accepted_plan is not None

    plan = result.accepted_plan
    assert plan.project_id == command.project_id
    assert plan.actor_user_id == "owner-1"
    assert plan.content_hash.startswith("sha256:")
    assert plan.original_filename == "knowledge.md"
    assert plan.source_format is SourceFormat.MARKDOWN
    assert plan.source_document_ref.startswith("source-document:project-1:")


@pytest.mark.asyncio
async def test_admin_accepted() -> None:
    command = _command(actor_user_id="admin-1")
    result = await _workflow_for_role("admin").execute(command)

    assert result.status is StartSourceIngestionWorkflowStatus.ACCEPTED
    assert result.accepted_plan is not None
    assert result.accepted_plan.actor_user_id == "admin-1"


@pytest.mark.asyncio
async def test_plan_identity_is_deterministic() -> None:
    workflow = _workflow_for_role("owner")

    command_one = _command(actor_user_id="owner-1")
    command_two = _command(actor_user_id="owner-1")
    different_content_command = _command(
        actor_user_id="owner-1",
        content_bytes=b"# Knowledge\n\nDifferent",
    )

    result_one = await workflow.execute(command_one)
    result_two = await workflow.execute(command_two)
    result_three = await workflow.execute(different_content_command)

    assert result_one.accepted_plan is not None
    assert result_two.accepted_plan is not None
    assert result_three.accepted_plan is not None

    assert (
        result_one.accepted_plan.content_hash == result_two.accepted_plan.content_hash
    )
    assert (
        result_one.accepted_plan.source_document_ref
        == result_two.accepted_plan.source_document_ref
    )
    assert (
        result_one.accepted_plan.source_document_ref
        != result_three.accepted_plan.source_document_ref
    )


def test_result_dataclasses_do_not_expose_content_bytes() -> None:
    result_fields = {field.name for field in fields(StartSourceIngestionWorkflowResult)}
    plan_fields = {field.name for field in fields(SourceIngestionAcceptedPlan)}

    assert "content_bytes" not in result_fields
    assert "content_bytes" not in plan_fields


def test_command_validation() -> None:
    with pytest.raises(ValueError, match="project_id must be non-empty"):
        _command(project_id=" ")

    with pytest.raises(ValueError, match="content_bytes must be non-empty"):
        _command(content_bytes=b"")

    with pytest.raises(ValueError, match="original_filename must be non-empty"):
        _command(original_filename=" ")

    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        _command(occurred_at=datetime(2026, 6, 10, 12, 0))


def test_result_validation_rejects_inconsistent_states() -> None:
    with pytest.raises(ValueError, match="accepted result requires accepted_plan"):
        StartSourceIngestionWorkflowResult(
            status=StartSourceIngestionWorkflowStatus.ACCEPTED,
            admission=_allowed_admission(),
        )

    with pytest.raises(ValueError, match="accepted result requires allowed admission"):
        StartSourceIngestionWorkflowResult(
            status=StartSourceIngestionWorkflowStatus.ACCEPTED,
            admission=_denied_admission(),
            accepted_plan=_accepted_plan(),
        )

    with pytest.raises(
        ValueError, match="rejected result must not include accepted_plan"
    ):
        StartSourceIngestionWorkflowResult(
            status=StartSourceIngestionWorkflowStatus.REJECTED,
            admission=_denied_admission(),
            accepted_plan=_accepted_plan(),
        )

    with pytest.raises(ValueError, match="rejected result requires denied admission"):
        StartSourceIngestionWorkflowResult(
            status=StartSourceIngestionWorkflowStatus.REJECTED,
            admission=_allowed_admission(),
        )


def test_start_source_ingestion_workflow_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "start_source_ingestion_workflow.py",
    ).read_text(encoding="utf-8")

    required_markers = [
        "StartSourceIngestionWorkflow",
        "StartSourceIngestionWorkflowCommand",
        "StartSourceIngestionWorkflowResult",
        "StartSourceIngestionWorkflowStatus",
        "SourceIngestionAcceptedPlan",
        "SourceIngestionAdmissionPolicy",
        "sha256",
        "content_hash",
        "source_document_ref",
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
        "SourceManagementRepositoryPort",
        "PostgresSourceManagementRepository",
        "KnowledgeExtractionSagaStateRepositoryPort",
        "RunClaimExtractionStageAsync",
        "DraftObservationExtractionSchedulingReconciler",
        "PROMPT_A",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
        "queue",
        "Queue",
        "save_source_document",
        "save_source_units",
        "save_workflow_state",
        "save_phase_checkpoint",
        "emit_command",
        "record_command",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
