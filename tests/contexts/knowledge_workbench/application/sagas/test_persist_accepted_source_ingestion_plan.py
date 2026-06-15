from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.persist_accepted_source_ingestion_plan import (
    PersistAcceptedSourceIngestionPlan,
    PersistAcceptedSourceIngestionPlanCommand,
    PersistAcceptedSourceIngestionPlanResult,
    PersistAcceptedSourceIngestionPlanSagaStatePort,
    PersistAcceptedSourceIngestionPlanSourceDocumentPort,
)
from src.contexts.knowledge_workbench.application.sagas.start_source_ingestion_workflow import (
    SourceIngestionAcceptedPlan,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)


class FakeSourceDocumentRepository:
    def __init__(self, *, fail_on_save: bool = False) -> None:
        self.saved_documents: list[SourceDocument] = []
        self.fail_on_save = fail_on_save

    async def save_source_document(self, document: SourceDocument) -> None:
        if self.fail_on_save:
            raise RuntimeError("source document save failed")
        self.saved_documents.append(document)


class FakeSagaStateRepository:
    def __init__(self, *, fail_on_save_workflow_state: bool = False) -> None:
        self.saved_states: list[KnowledgeExtractionWorkflowState] = []
        self.saved_checkpoints: list[KnowledgeExtractionPhaseCheckpoint] = []
        self.fail_on_save_workflow_state = fail_on_save_workflow_state

    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None:
        if self.fail_on_save_workflow_state:
            raise RuntimeError("workflow state save failed")
        self.saved_states.append(state)

    async def save_phase_checkpoint(
        self,
        checkpoint: KnowledgeExtractionPhaseCheckpoint,
    ) -> None:
        self.saved_checkpoints.append(checkpoint)


class FakeUnitOfWork:
    def __init__(
        self,
        *,
        source_management: FakeSourceDocumentRepository | None = None,
        saga_state: FakeSagaStateRepository | None = None,
    ) -> None:
        self.source_document_repository = (
            source_management or FakeSourceDocumentRepository()
        )
        self.saga_state_repository = saga_state or FakeSagaStateRepository()
        self.source_management: PersistAcceptedSourceIngestionPlanSourceDocumentPort = (
            self.source_document_repository
        )
        self.saga_state: PersistAcceptedSourceIngestionPlanSagaStatePort = (
            self.saga_state_repository
        )
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


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


def _use_case(
    unit_of_work: FakeUnitOfWork,
) -> PersistAcceptedSourceIngestionPlan:
    return PersistAcceptedSourceIngestionPlan(unit_of_work=unit_of_work)


@pytest.mark.asyncio
async def test_persists_source_document_and_saga_state() -> None:
    unit_of_work = FakeUnitOfWork()
    accepted_plan = _accepted_plan()

    result = await _use_case(unit_of_work).execute(
        PersistAcceptedSourceIngestionPlanCommand(accepted_plan=accepted_plan),
    )

    assert len(unit_of_work.source_document_repository.saved_documents) == 1
    document = unit_of_work.source_document_repository.saved_documents[0]
    assert document.document_ref.value == accepted_plan.source_document_ref
    assert document.project_id == accepted_plan.project_id
    assert document.source_format is accepted_plan.source_format
    assert document.content_hash == accepted_plan.content_hash
    assert document.original_filename == accepted_plan.original_filename
    assert document.created_at == accepted_plan.occurred_at

    assert len(unit_of_work.saga_state_repository.saved_states) == 1
    state = unit_of_work.saga_state_repository.saved_states[0]
    assert state.project_id == accepted_plan.project_id
    assert state.source_document_ref == accepted_plan.source_document_ref
    assert state.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert state.current_phase is KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED
    assert state.created_at == accepted_plan.occurred_at
    assert state.updated_at == accepted_plan.occurred_at

    assert len(unit_of_work.saga_state_repository.saved_checkpoints) == 2
    assert tuple(
        checkpoint.phase_key
        for checkpoint in unit_of_work.saga_state_repository.saved_checkpoints
    ) == (
        KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
        KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
    )

    assert result.workflow_run_id == (
        f"knowledge-extraction:{accepted_plan.source_document_ref}"
    )
    assert result.source_document_ref == accepted_plan.source_document_ref
    assert result.document_checkpoint_status is KnowledgeExtractionPhaseStatus.COMPLETED
    assert result.source_document_persisted is True


@pytest.mark.asyncio
async def test_checkpoints_payloads_are_useful_and_deterministic() -> None:
    unit_of_work = FakeUnitOfWork()
    accepted_plan = _accepted_plan()

    await _use_case(unit_of_work).execute(
        PersistAcceptedSourceIngestionPlanCommand(accepted_plan=accepted_plan),
    )

    document_accepted = unit_of_work.saga_state_repository.saved_checkpoints[0]
    source_document_persisted = unit_of_work.saga_state_repository.saved_checkpoints[1]

    assert document_accepted.phase_key is KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED
    assert document_accepted.idempotency_key == (
        f"document-accepted:{accepted_plan.source_document_ref}"
    )
    assert document_accepted.checkpoint_payload["actor_user_id"] == "owner-1"
    assert document_accepted.checkpoint_payload["original_filename"] == "knowledge.md"
    assert document_accepted.checkpoint_payload["source_format"] == "markdown"
    assert document_accepted.checkpoint_payload["content_hash"] == "sha256:abc"

    assert (
        source_document_persisted.phase_key
        is KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED
    )
    assert source_document_persisted.idempotency_key == (
        f"source-document-persisted:{accepted_plan.source_document_ref}"
    )
    assert (
        source_document_persisted.checkpoint_payload["source_document_ref"]
        == accepted_plan.source_document_ref
    )
    assert source_document_persisted.checkpoint_payload["content_hash"] == "sha256:abc"


@pytest.mark.asyncio
async def test_workflow_run_id_is_deterministic() -> None:
    accepted_plan = _accepted_plan()

    result_one = await _use_case(FakeUnitOfWork()).execute(
        PersistAcceptedSourceIngestionPlanCommand(accepted_plan=accepted_plan),
    )
    result_two = await _use_case(FakeUnitOfWork()).execute(
        PersistAcceptedSourceIngestionPlanCommand(accepted_plan=accepted_plan),
    )

    assert result_one.workflow_run_id == result_two.workflow_run_id


@pytest.mark.asyncio
async def test_does_not_persist_source_units_or_future_phases() -> None:
    unit_of_work = FakeUnitOfWork()

    await _use_case(unit_of_work).execute(
        PersistAcceptedSourceIngestionPlanCommand(accepted_plan=_accepted_plan()),
    )

    assert not hasattr(unit_of_work.source_document_repository, "save_source_units")

    saved_phase_keys = {
        checkpoint.phase_key
        for checkpoint in unit_of_work.saga_state_repository.saved_checkpoints
    }
    assert KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED not in saved_phase_keys
    assert (
        KnowledgeExtractionPhaseKey.CLAIM_BUILDER_WORK_SCHEDULED not in saved_phase_keys
    )


@pytest.mark.asyncio
async def test_commit_called_on_success() -> None:
    unit_of_work = FakeUnitOfWork()

    await _use_case(unit_of_work).execute(
        PersistAcceptedSourceIngestionPlanCommand(accepted_plan=_accepted_plan()),
    )

    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 0


@pytest.mark.asyncio
async def test_rollback_called_on_source_document_failure() -> None:
    unit_of_work = FakeUnitOfWork(
        source_management=FakeSourceDocumentRepository(fail_on_save=True),
    )

    with pytest.raises(RuntimeError, match="source document save failed"):
        await _use_case(unit_of_work).execute(
            PersistAcceptedSourceIngestionPlanCommand(accepted_plan=_accepted_plan()),
        )

    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 1


@pytest.mark.asyncio
async def test_rollback_called_on_workflow_state_failure() -> None:
    unit_of_work = FakeUnitOfWork(
        saga_state=FakeSagaStateRepository(fail_on_save_workflow_state=True),
    )

    with pytest.raises(RuntimeError, match="workflow state save failed"):
        await _use_case(unit_of_work).execute(
            PersistAcceptedSourceIngestionPlanCommand(accepted_plan=_accepted_plan()),
        )

    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 1


def test_validation_rejects_wrong_command_and_result_shapes() -> None:
    with pytest.raises(
        TypeError, match="accepted_plan must be SourceIngestionAcceptedPlan"
    ):
        PersistAcceptedSourceIngestionPlanCommand(
            accepted_plan=cast(SourceIngestionAcceptedPlan, object()),
        )

    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        PersistAcceptedSourceIngestionPlanResult(
            workflow_run_id="",
            source_document_ref="source-document:project-1:abc",
            document_checkpoint_status=KnowledgeExtractionPhaseStatus.COMPLETED,
            source_document_persisted=True,
        )

    with pytest.raises(ValueError, match="source_document_ref must be non-empty"):
        PersistAcceptedSourceIngestionPlanResult(
            workflow_run_id="workflow-1",
            source_document_ref="",
            document_checkpoint_status=KnowledgeExtractionPhaseStatus.COMPLETED,
            source_document_persisted=True,
        )

    with pytest.raises(
        TypeError,
        match="document_checkpoint_status must be KnowledgeExtractionPhaseStatus",
    ):
        PersistAcceptedSourceIngestionPlanResult(
            workflow_run_id="workflow-1",
            source_document_ref="source-document:project-1:abc",
            document_checkpoint_status=cast(
                KnowledgeExtractionPhaseStatus,
                "COMPLETED",
            ),
            source_document_persisted=True,
        )


def test_persist_accepted_source_ingestion_plan_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "persist_accepted_source_ingestion_plan.py",
    ).read_text(encoding="utf-8")

    required_markers = [
        "PersistAcceptedSourceIngestionPlan",
        "PersistAcceptedSourceIngestionPlanCommand",
        "PersistAcceptedSourceIngestionPlanResult",
        "PersistAcceptedSourceIngestionPlanUnitOfWorkPort",
        "SourceDocument",
        "KnowledgeExtractionWorkflowState",
        "DOCUMENT_ACCEPTED",
        "SOURCE_DOCUMENT_PERSISTED",
        "save_source_document",
        "save_workflow_state",
        "save_phase_checkpoint",
        "commit",
        "rollback",
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
        "SourceParserPort",
        "SourceUnit",
        "save_source_units",
        "RunClaimExtractionStageAsync",
        "PROMPT_A",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
        "queue",
        "Queue",
        "emit_command",
        "record_command",
        "event_was_processed",
        "record_processed_event",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
