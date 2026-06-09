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
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_source_phase_reconciliation import (
    KnowledgeExtractionSourcePhaseReconciler,
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
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)

ROOT = Path(__file__).resolve().parents[5]
SAGA_SOURCE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "application"
    / "sagas"
    / "knowledge_extraction_saga.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _state(
    checkpoints: tuple[KnowledgeExtractionPhaseCheckpoint, ...] = (),
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id="workflow-1",
        project_id="project-1",
        source_document_ref="source-document-1",
        status=KnowledgeExtractionWorkflowStatus.RUNNING,
        current_phase=KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        checkpoints=checkpoints,
    )


def _document() -> SourceDocument:
    return SourceDocument(
        SourceDocumentRef("source-document-1"),
        "project-1",
        SourceFormat.MARKDOWN,
        "sha256:abc",
        _now(),
        "knowledge.md",
    )


def _unit(unit_ref: str, ordinal: int) -> SourceUnit:
    return SourceUnit(
        SourceUnitRef(unit_ref),
        SourceDocumentRef("source-document-1"),
        SourceUnitKind.SECTION,
        SourceUnitText("section"),
        HeadingPath(("Section",)),
        SourceUnitLineage(),
        ordinal,
        _now(),
    )


class _StateRepository(KnowledgeExtractionSagaStateRepositoryPort):
    def __init__(self, state: KnowledgeExtractionWorkflowState | None) -> None:
        self.state = state
        self.saved_states: list[KnowledgeExtractionWorkflowState] = []
        self.saved_checkpoints: list[KnowledgeExtractionPhaseCheckpoint] = []

    async def load_workflow_state(
        self, workflow_run_id: str
    ) -> KnowledgeExtractionWorkflowState | None:
        return self.state

    async def save_workflow_state(
        self, state: KnowledgeExtractionWorkflowState
    ) -> None:
        self.saved_states.append(state)

    async def save_phase_checkpoint(
        self, checkpoint: KnowledgeExtractionPhaseCheckpoint
    ) -> None:
        self.saved_checkpoints.append(checkpoint)


class _CommandLog(KnowledgeExtractionCommandLogPort):
    def __init__(self) -> None:
        self.commands: list[KnowledgeExtractionCommandRecord] = []

    async def command_exists(self, command_key: str) -> bool:
        return False

    async def record_command(self, command: KnowledgeExtractionCommandRecord) -> None:
        self.commands.append(command)


class _EventCursor(KnowledgeExtractionEventCursorPort):
    def __init__(self) -> None:
        self.events: list[KnowledgeExtractionEventCursorRecord] = []

    async def event_was_processed(self, *, consumer_name: str, event_id: str) -> bool:
        return False

    async def record_processed_event(
        self, record: KnowledgeExtractionEventCursorRecord
    ) -> None:
        self.events.append(record)


class _CommandEmitter(KnowledgeExtractionCommandEmitterPort):
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


class _SourceRepository(SourceManagementRepositoryPort):
    def __init__(
        self, document: SourceDocument | None, units: tuple[SourceUnit, ...] = ()
    ) -> None:
        self.document = document
        self.units = units
        self.listed_refs: list[SourceDocumentRef] = []

    async def save_source_document(self, document: SourceDocument) -> None:
        raise AssertionError("must not save documents")

    async def load_source_document(
        self, document_ref: SourceDocumentRef
    ) -> SourceDocument | None:
        return self.document

    async def save_source_units(self, units: tuple[SourceUnit, ...]) -> None:
        raise AssertionError("must not save units")

    async def list_source_units_for_document(
        self, document_ref: SourceDocumentRef
    ) -> tuple[SourceUnit, ...]:
        self.listed_refs.append(document_ref)
        return self.units

    async def load_source_unit(self, unit_ref: SourceUnitRef) -> SourceUnit | None:
        return None


def _saga(
    state_repository: _StateRepository,
    source_repository: _SourceRepository | None = None,
) -> tuple[KnowledgeExtractionSaga, _CommandLog, _EventCursor, _CommandEmitter]:
    command_log = _CommandLog()
    event_cursor = _EventCursor()
    command_emitter = _CommandEmitter()
    reconciler = (
        None
        if source_repository is None
        else KnowledgeExtractionSourcePhaseReconciler(
            source_repository=source_repository
        )
    )
    saga = KnowledgeExtractionSaga(
        state_repository=state_repository,
        command_log=command_log,
        event_cursor=event_cursor,
        command_emitter=command_emitter,
        source_phase_reconciler=reconciler,
    )
    return saga, command_log, event_cursor, command_emitter


@pytest.mark.asyncio
async def test_existing_behavior_is_unchanged_without_source_reconciler() -> None:
    state_repository = _StateRepository(_state())
    saga, command_log, event_cursor, command_emitter = _saga(state_repository)

    result = await saga.reconcile(
        ReconcileKnowledgeExtractionSagaCommand("workflow-1", _now())
    )

    assert result.current_phase is KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED
    assert result.emitted_command_count == 0
    assert state_repository.saved_checkpoints == []
    assert state_repository.saved_states == []
    assert command_log.commands == []
    assert event_cursor.events == []
    assert command_emitter.commands == []


@pytest.mark.asyncio
async def test_missing_source_document_saves_blocked_checkpoint_and_pauses() -> None:
    state_repository = _StateRepository(_state())
    source_repository = _SourceRepository(None)
    saga, command_log, event_cursor, command_emitter = _saga(
        state_repository, source_repository
    )

    result = await saga.reconcile(
        ReconcileKnowledgeExtractionSagaCommand("workflow-1", _now())
    )

    assert [
        checkpoint.phase_key for checkpoint in state_repository.saved_checkpoints
    ] == [
        KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
    ]
    assert (
        state_repository.saved_checkpoints[0].phase_status
        is KnowledgeExtractionPhaseStatus.BLOCKED
    )
    assert (
        state_repository.saved_checkpoints[1].phase_status
        is KnowledgeExtractionPhaseStatus.NOT_STARTED
    )
    assert len(state_repository.saved_states) == 1
    assert (
        state_repository.saved_states[0].status
        is KnowledgeExtractionWorkflowStatus.PAUSED
    )
    assert (
        state_repository.saved_states[0].current_phase
        is KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED
    )
    assert state_repository.saved_states[0].pause_reason == "source_document_missing"
    assert source_repository.listed_refs == []
    assert result.emitted_command_count == 0
    assert command_log.commands == []
    assert event_cursor.events == []
    assert command_emitter.commands == []


@pytest.mark.asyncio
async def test_source_document_present_but_units_missing_pauses_at_source_units() -> (
    None
):
    state_repository = _StateRepository(_state())
    saga, _, _, _ = _saga(state_repository, _SourceRepository(_document()))

    result = await saga.reconcile(
        ReconcileKnowledgeExtractionSagaCommand("workflow-1", _now())
    )

    assert (
        state_repository.saved_checkpoints[0].phase_status
        is KnowledgeExtractionPhaseStatus.COMPLETED
    )
    assert (
        state_repository.saved_checkpoints[1].phase_status
        is KnowledgeExtractionPhaseStatus.NOT_STARTED
    )
    assert (
        state_repository.saved_states[0].status
        is KnowledgeExtractionWorkflowStatus.PAUSED
    )
    assert (
        state_repository.saved_states[0].current_phase
        is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    )
    assert state_repository.saved_states[0].pause_reason == "source_units_missing"
    assert result.emitted_command_count == 0


@pytest.mark.asyncio
async def test_source_document_and_units_present_completes_source_checkpoints() -> None:
    state_repository = _StateRepository(_state())
    units = (_unit("source-document-1.unit.0", 0), _unit("source-document-1.unit.1", 1))
    saga, _, _, _ = _saga(state_repository, _SourceRepository(_document(), units))

    result = await saga.reconcile(
        ReconcileKnowledgeExtractionSagaCommand("workflow-1", _now())
    )

    assert (
        state_repository.saved_checkpoints[0].phase_status
        is KnowledgeExtractionPhaseStatus.COMPLETED
    )
    assert (
        state_repository.saved_checkpoints[1].phase_status
        is KnowledgeExtractionPhaseStatus.COMPLETED
    )
    assert state_repository.saved_checkpoints[1].completed_count == 2
    assert (
        state_repository.saved_states[0].status
        is KnowledgeExtractionWorkflowStatus.RUNNING
    )
    assert (
        state_repository.saved_states[0].current_phase
        is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    )
    assert state_repository.saved_states[0].pause_reason is None
    assert result.current_phase is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert result.emitted_command_count == 0


@pytest.mark.asyncio
async def test_replaces_existing_source_checkpoints_in_saved_state() -> None:
    old_checkpoint = KnowledgeExtractionPhaseCheckpoint(
        "workflow-1",
        KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        KnowledgeExtractionPhaseStatus.NOT_STARTED,
    )
    state_repository = _StateRepository(_state((old_checkpoint,)))
    saga, _, _, _ = _saga(
        state_repository,
        _SourceRepository(_document(), (_unit("source-document-1.unit.0", 0),)),
    )

    await saga.reconcile(ReconcileKnowledgeExtractionSagaCommand("workflow-1", _now()))

    phase_keys = [
        checkpoint.phase_key
        for checkpoint in state_repository.saved_states[0].checkpoints
    ]
    assert phase_keys.count(KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED) == 1
    assert phase_keys.count(KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED) == 1


def test_source_guard() -> None:
    text = SAGA_SOURCE.read_text(encoding="utf-8")
    required_markers = (
        "KnowledgeExtractionSourcePhaseReconciler",
        "_source_phase_reconciler",
        "save_phase_checkpoint",
        "KnowledgeExtractionPhaseCheckpoint",
        "SOURCE_DOCUMENT_PERSISTED",
        "SOURCE_UNITS_CREATED",
        "source_document_missing",
        "source_units_missing",
    )
    forbidden_markers = (
        "emit_command(",
        "record_command(",
        "event_was_processed(",
        "record_processed_event(",
        "PostgresSourceManagementRepository",
        "PostgresKnowledgeExtractionSagaStateRepository",
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
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "knowledge_workbench_documents",
        "knowledge_workbench_document_sections",
        "knowledge_workbench_processing_runs",
        "SectionBatchQueueItem",
        "workbench_parallel_processing",
        "process_workbench_document",
        "RunClaimExtractionStageAsync",
        "RecordClaimExtractionSuccess",
        "ProcessClaimExtractionWorkItem",
        "ApplyDraftClaimObservationArtifactAsync",
        "PROMPT_A_WORK_SCHEDULED",
    )
    assert not [marker for marker in required_markers if marker not in text]
    assert not [marker for marker in forbidden_markers if marker in text]
