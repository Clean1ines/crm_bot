from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import pytest

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


ROOT = Path(__file__).resolve().parents[5]
SAGA_DIR = ROOT / "src" / "contexts" / "knowledge_workbench" / "application" / "sagas"


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def test_phase_vocabulary_matches_document() -> None:
    assert tuple(phase.value for phase in KnowledgeExtractionPhaseKey) == (
        "DOCUMENT_ACCEPTED",
        "SOURCE_DOCUMENT_PERSISTED",
        "SOURCE_UNITS_CREATED",
        "PROMPT_A_WORK_SCHEDULED",
        "PROMPT_A_WORK_COMPLETED",
        "PROMPT_A_ARTIFACTS_APPLIED",
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
        checkpoint.checkpoint_payload["source_units"] = 4

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


@pytest.mark.asyncio
async def test_saga_reconcile_returns_existing_state_without_emitting_commands() -> (
    None
):
    state = KnowledgeExtractionWorkflowState(
        workflow_run_id="workflow-1",
        project_id="project-1",
        source_document_ref="source-document-1",
        status=KnowledgeExtractionWorkflowStatus.RUNNING,
        current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
    )
    command_emitter = _FakeCommandEmitter()
    saga = KnowledgeExtractionSaga(
        state_repository=_FakeStateRepository(state),
        command_log=_FakeCommandLog(),
        event_cursor=_FakeEventCursor(),
        command_emitter=command_emitter,
    )

    result = await saga.reconcile(
        ReconcileKnowledgeExtractionSagaCommand(
            workflow_run_id="workflow-1",
            occurred_at=_now(),
        )
    )

    assert result.workflow_run_id == "workflow-1"
    assert result.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert result.current_phase is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert result.emitted_command_count == 0
    assert command_emitter.commands == []


@pytest.mark.asyncio
async def test_saga_reconcile_rejects_missing_state() -> None:
    saga = KnowledgeExtractionSaga(
        state_repository=_FakeStateRepository(None),
        command_log=_FakeCommandLog(),
        event_cursor=_FakeEventCursor(),
        command_emitter=_FakeCommandEmitter(),
    )

    with pytest.raises(ValueError):
        await saga.reconcile(
            ReconcileKnowledgeExtractionSagaCommand(
                workflow_run_id="workflow-1",
                occurred_at=_now(),
            )
        )


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
        "postgres",
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
        "process_workbench_document",
        "RunClaimExtractionStageAsync",
        "RecordClaimExtractionSuccess",
        "ProcessClaimExtractionWorkItem",
        "ApplyDraftClaimObservationArtifactAsync",
    )

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
