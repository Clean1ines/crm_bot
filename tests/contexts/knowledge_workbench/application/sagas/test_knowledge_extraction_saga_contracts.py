from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.knowledge_workbench.application.sagas import (
    KnowledgeExtractionCommandEmitterPort,
    KnowledgeExtractionCommandLogPort,
    KnowledgeExtractionCommandRecord,
    KnowledgeExtractionEventCursorPort,
    KnowledgeExtractionEventCursorRecord,
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionSaga,
    KnowledgeExtractionSagaStateRepositoryPort,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
    ReconcileKnowledgeExtractionSagaCommand,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_reconcile_unit_of_work import (
    KnowledgeExtractionSagaReconcileUnitOfWorkPort,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


ROOT = Path(__file__).resolve().parents[5]
SAGA_DIR = ROOT / "src" / "contexts" / "knowledge_workbench" / "application" / "sagas"


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def test_phase_vocabulary_matches_document() -> None:
    assert tuple(phase.value for phase in KnowledgeExtractionPhaseKey) == (
        "DOCUMENT_ACCEPTED",
        "SOURCE_DOCUMENT_PERSISTED",
        "SOURCE_UNITS_CREATED",
        "CLAIM_BUILDER_WORK_SCHEDULED",
        "CLAIM_BUILDER_SECTION_EXTRACTION_COMPLETED",
        "CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED",
        "DRAFT_EMBEDDINGS_BUILT",
        "DRAFT_CLUSTERS_BUILT",
        "PROMPT_B_WORK_SCHEDULED",
        "PROMPT_B_WORK_COMPLETED",
        "FINAL_KNOWLEDGE_PREPARED",
        "WAITING_FOR_REVIEW",
        "REVIEW_COMPLETED",
        "PUBLISHED",
        "RETRIEVAL_EMBEDDINGS_BUILT",
        "INTERMEDIATE_ARTIFACTS_CLEANED",
        "DONE",
    )


def test_workflow_status_vocabulary_matches_document() -> None:
    assert tuple(status.value for status in KnowledgeExtractionWorkflowStatus) == (
        "CREATED",
        "RUNNING",
        "PAUSED",
        "WAITING_FOR_EXTERNAL_EVENT",
        "WAITING_FOR_REVIEW",
        "FAILED",
        "CANCELLED",
        "COMPLETED",
    )


def test_phase_status_vocabulary_matches_document() -> None:
    assert tuple(status.value for status in KnowledgeExtractionPhaseStatus) == (
        "NOT_STARTED",
        "READY",
        "IN_PROGRESS",
        "WAITING",
        "BLOCKED",
        "COMPLETED",
        "SKIPPED",
        "FAILED",
        "CANCELLED",
    )


def test_checkpoint_validates_counts_and_freezes_payload() -> None:
    payload = {"source_units": 2}
    checkpoint = KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id="workflow-1",
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        expected_count=2,
        completed_count=2,
        checkpoint_payload=payload,
    )

    payload["source_units"] = 3

    assert checkpoint.checkpoint_payload["source_units"] == 2
    with pytest.raises(TypeError):
        cast(dict[str, object], checkpoint.checkpoint_payload)["source_units"] = 4

    with pytest.raises(ValueError):
        KnowledgeExtractionPhaseCheckpoint(
            workflow_run_id="workflow-1",
            phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
            phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
            expected_count=2,
            completed_count=1,
            failed_count=1,
            blocked_count=1,
        )

    with pytest.raises(ValueError):
        KnowledgeExtractionPhaseCheckpoint(
            workflow_run_id="workflow-1",
            phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
            phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
            expected_count=-1,
        )


def test_workflow_state_validates_checkpoint_ownership_and_terminal_timestamps() -> (
    None
):
    checkpoint = KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id="other-workflow",
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
    )

    with pytest.raises(ValueError):
        KnowledgeExtractionWorkflowState(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document-1",
            status=KnowledgeExtractionWorkflowStatus.RUNNING,
            current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
            checkpoints=(checkpoint,),
        )

    duplicate_checkpoint = KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id="workflow-1",
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
    )

    with pytest.raises(ValueError):
        KnowledgeExtractionWorkflowState(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document-1",
            status=KnowledgeExtractionWorkflowStatus.RUNNING,
            current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
            checkpoints=(duplicate_checkpoint, duplicate_checkpoint),
        )

    with pytest.raises(ValueError):
        KnowledgeExtractionWorkflowState(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document-1",
            status=KnowledgeExtractionWorkflowStatus.COMPLETED,
            current_phase=KnowledgeExtractionPhaseKey.DONE,
        )

    with pytest.raises(ValueError):
        KnowledgeExtractionWorkflowState(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document-1",
            status=KnowledgeExtractionWorkflowStatus.CANCELLED,
            current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        )

    with pytest.raises(ValueError):
        KnowledgeExtractionWorkflowState(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document-1",
            status=KnowledgeExtractionWorkflowStatus.FAILED,
            current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        )

    with pytest.raises(ValueError):
        KnowledgeExtractionWorkflowState(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document-1",
            status=KnowledgeExtractionWorkflowStatus.WAITING_FOR_REVIEW,
            current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        )


def test_command_and_event_records_validate_strings_and_time_ordering() -> None:
    with pytest.raises(ValueError):
        KnowledgeExtractionCommandRecord(
            command_key=" ",
            workflow_run_id="workflow-1",
            phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
            target_context="knowledge_workbench/source_management",
            command_kind="CreateSourceUnits",
            command_payload_hash="hash-1",
            status="emitted",
            emitted_at=_now(),
        )

    with pytest.raises(ValueError):
        KnowledgeExtractionCommandRecord(
            command_key="command-1",
            workflow_run_id="workflow-1",
            phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
            target_context="knowledge_workbench/source_management",
            command_kind="CreateSourceUnits",
            command_payload_hash="hash-1",
            status="completed",
            emitted_at=datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 6, 9, 11, 0, tzinfo=timezone.utc),
        )

    with pytest.raises(ValueError):
        KnowledgeExtractionEventCursorRecord(
            consumer_name="knowledge-extraction-saga",
            event_id=" ",
            workflow_run_id="workflow-1",
            event_type="SourceUnitCreated",
            processed_at=_now(),
            handler_result="ignored",
        )


class _FakeStateRepository(KnowledgeExtractionSagaStateRepositoryPort):
    def __init__(self, state: KnowledgeExtractionWorkflowState | None) -> None:
        self._state = state
        self.saved_states: list[KnowledgeExtractionWorkflowState] = []
        self.saved_checkpoints: list[KnowledgeExtractionPhaseCheckpoint] = []

    async def load_workflow_state(
        self,
        workflow_run_id: str,
    ) -> KnowledgeExtractionWorkflowState | None:
        return self._state

    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None:
        self.saved_states.append(state)

    async def save_phase_checkpoint(
        self,
        checkpoint: KnowledgeExtractionPhaseCheckpoint,
    ) -> None:
        self.saved_checkpoints.append(checkpoint)


class _FakeCommandLog(KnowledgeExtractionCommandLogPort):
    def __init__(self) -> None:
        self.commands: list[KnowledgeExtractionCommandRecord] = []

    async def command_exists(self, command_key: str) -> bool:
        return False

    async def record_command(
        self,
        command: KnowledgeExtractionCommandRecord,
    ) -> None:
        self.commands.append(command)


class _FakeEventCursor(KnowledgeExtractionEventCursorPort):
    def __init__(self) -> None:
        self.events: list[KnowledgeExtractionEventCursorRecord] = []

    async def event_was_processed(
        self,
        *,
        consumer_name: str,
        event_id: str,
    ) -> bool:
        return False

    async def record_processed_event(
        self,
        record: KnowledgeExtractionEventCursorRecord,
    ) -> None:
        self.events.append(record)


class _FakeCommandEmitter(KnowledgeExtractionCommandEmitterPort):
    def __init__(self) -> None:
        self.commands: list[Mapping[str, object]] = []

    async def emit_command(
        self,
        *,
        command_key: str,
        target_context: str,
        command_kind: str,
        payload: Mapping[str, object],
    ) -> None:
        self.commands.append(
            {
                "command_key": command_key,
                "target_context": target_context,
                "command_kind": command_kind,
                "payload": dict(payload),
            }
        )


class _UnusedSourceManagementRepository(SourceManagementRepositoryPort):
    async def save_source_document(self, document: SourceDocument) -> None:
        raise AssertionError("source management repository should not be used")

    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None:
        raise AssertionError("source management repository should not be used")

    async def save_source_units(self, units: tuple[SourceUnit, ...]) -> None:
        raise AssertionError("source management repository should not be used")

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        raise AssertionError("source management repository should not be used")

    async def load_source_unit(self, unit_ref: SourceUnitRef) -> SourceUnit | None:
        raise AssertionError("source management repository should not be used")


class _UnusedWorkItemSchedulingRepository(WorkItemSchedulingRepositoryPort):
    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        raise AssertionError("work item scheduling repository should not be used")

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        raise AssertionError("work item scheduling repository should not be used")

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: Mapping[str, object],
    ) -> None:
        raise AssertionError("work item scheduling repository should not be used")


class _FakeSagaReconcileUnitOfWork(KnowledgeExtractionSagaReconcileUnitOfWorkPort):
    def __init__(
        self,
        *,
        state_repository: KnowledgeExtractionSagaStateRepositoryPort,
        command_log: KnowledgeExtractionCommandLogPort | None = None,
        event_cursor: KnowledgeExtractionEventCursorPort | None = None,
        command_emitter: KnowledgeExtractionCommandEmitterPort | None = None,
    ) -> None:
        self._state_repository = state_repository
        self._command_log = command_log or _FakeCommandLog()
        self._event_cursor = event_cursor or _FakeEventCursor()
        self._command_emitter = command_emitter or _FakeCommandEmitter()
        self._source_management_repository = _UnusedSourceManagementRepository()
        self._work_item_scheduling_repository = _UnusedWorkItemSchedulingRepository()
        self.commit_count = 0
        self.rollback_count = 0

    @property
    def saga_state_repository(self) -> KnowledgeExtractionSagaStateRepositoryPort:
        return self._state_repository

    @property
    def command_log(self) -> KnowledgeExtractionCommandLogPort:
        return self._command_log

    @property
    def event_cursor(self) -> KnowledgeExtractionEventCursorPort:
        return self._event_cursor

    @property
    def command_emitter(self) -> KnowledgeExtractionCommandEmitterPort:
        return self._command_emitter

    @property
    def source_management_repository(self) -> SourceManagementRepositoryPort:
        return self._source_management_repository

    @property
    def work_item_scheduling_repository(self) -> WorkItemSchedulingRepositoryPort:
        return self._work_item_scheduling_repository

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_saga_reconcile_returns_existing_state_without_emitting_commands() -> (
    None
):
    state = KnowledgeExtractionWorkflowState(
        workflow_run_id="workflow-1",
        project_id="project-1",
        source_document_ref="source-document-1",
        status=KnowledgeExtractionWorkflowStatus.RUNNING,
        current_phase=KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
    )
    command_emitter = _FakeCommandEmitter()
    unit_of_work = _FakeSagaReconcileUnitOfWork(
        state_repository=_FakeStateRepository(state),
        command_emitter=command_emitter,
    )
    saga = KnowledgeExtractionSaga(unit_of_work=unit_of_work)

    result = await saga.reconcile(
        ReconcileKnowledgeExtractionSagaCommand(
            workflow_run_id="workflow-1",
            occurred_at=_now(),
        )
    )

    assert result.workflow_run_id == "workflow-1"
    assert result.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert result.current_phase is KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED
    assert result.emitted_command_count == 0
    assert command_emitter.commands == []
    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 0


@pytest.mark.asyncio
async def test_saga_reconcile_rejects_missing_state() -> None:
    unit_of_work = _FakeSagaReconcileUnitOfWork(
        state_repository=_FakeStateRepository(None),
    )
    saga = KnowledgeExtractionSaga(unit_of_work=unit_of_work)

    with pytest.raises(ValueError):
        await saga.reconcile(
            ReconcileKnowledgeExtractionSagaCommand(
                workflow_run_id="workflow-1",
                occurred_at=_now(),
            )
        )

    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 1


def test_source_guard() -> None:
    paths = (
        SAGA_DIR / "knowledge_extraction_saga.py",
        SAGA_DIR / "knowledge_extraction_saga_state.py",
        SAGA_DIR / "knowledge_extraction_saga_ports.py",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    required_markers = (
        "KnowledgeExtractionSaga",
        "ReconcileKnowledgeExtractionSagaCommand",
        "KnowledgeExtractionWorkflowState",
        "KnowledgeExtractionPhaseKey",
        "KnowledgeExtractionWorkflowStatus",
        "KnowledgeExtractionSagaStateRepositoryPort",
        "KnowledgeExtractionCommandLogPort",
        "KnowledgeExtractionEventCursorPort",
        "KnowledgeExtractionCommandEmitterPort",
    )
    forbidden_markers = (
        "asyncpg",
        "post" + "gres",
        "Postgres",
        "src.infrastructure",
        "JobDispatcher",
        "worker_loop",
        "outbox_events",
        "published_at",
        "Groq",
        "Qwen",
        "src.contexts.execution_runtime.infrastructure",
        "src.contexts.llm_runtime.infrastructure",
        "src.contexts.artifact_runtime.infrastructure",
        "knowledge_workbench_processing_runs",
        "SectionBatchQueueItem",
        "workbench_parallel_processing",
        "process_" + "workbench_document",
        "RunClaimExtractionStageAsync",
        "RecordClaimExtractionSuccess",
        "ProcessClaimExtractionWorkItem",
        "ApplyDraftClaimObservationArtifactAsync",
    )

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)


def test_application_sagas_do_not_import_infrastructure_runtime_boundaries() -> None:
    paths = tuple(sorted(SAGA_DIR.glob("*.py")))
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    forbidden_markers = (
        "src.infrastructure",
        "asyncpg",
        "post" + "gres",
        "Postgres",
        "worker_loop",
        "JobDispatcher",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders, "\n".join(offenders)
