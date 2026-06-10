from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.ports.work_item_scheduling_unit_of_work_port import (
    WorkItemSchedulingUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.advance_to_draft_observation_scheduling_phase import (
    AdvanceToDraftObservationSchedulingPhase,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga import (
    KnowledgeExtractionSaga,
    ReconcileKnowledgeExtractionSagaCommand,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionCommandEmitterPort,
    KnowledgeExtractionCommandLogPort,
    KnowledgeExtractionCommandRecord,
    KnowledgeExtractionEventCursorPort,
    KnowledgeExtractionEventCursorRecord,
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_source_phase_reconciliation import (
    KnowledgeExtractionSourcePhaseReconciler,
)
from src.contexts.knowledge_workbench.application.sagas.schedule_draft_observation_extraction_work import (
    ScheduleDraftObservationExtractionWork,
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


@dataclass(frozen=True, slots=True)
class SavedScheduledWorkItem:
    item: WorkItem
    idempotency_key: str
    payload_hash: str
    payload: Mapping[str, object]


@dataclass(slots=True)
class FakeWorkItemSchedulingUnitOfWork:
    existing_items: dict[str, WorkItem] = field(default_factory=dict)
    schedule_payload_hashes: dict[str, str] = field(default_factory=dict)
    saved: list[SavedScheduledWorkItem] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False

    def get_work_item(self, work_item_id: str) -> WorkItem | None:
        return self.existing_items.get(work_item_id)

    def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        return self.schedule_payload_hashes.get(work_item_id)

    def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: Mapping[str, object],
    ) -> None:
        self.saved.append(
            SavedScheduledWorkItem(
                item=item,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                payload=payload,
            ),
        )
        self.existing_items[item.work_item_id] = item
        self.schedule_payload_hashes[item.work_item_id] = payload_hash

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeStateRepository(KnowledgeExtractionSagaStateRepositoryPort):
    def __init__(self, state: KnowledgeExtractionWorkflowState | None) -> None:
        self.state = state
        self.saved_states: list[KnowledgeExtractionWorkflowState] = []
        self.saved_checkpoints: list[KnowledgeExtractionPhaseCheckpoint] = []

    async def load_workflow_state(
        self,
        workflow_run_id: str,
    ) -> KnowledgeExtractionWorkflowState | None:
        return self.state

    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None:
        self.saved_states.append(state)
        self.state = state

    async def save_phase_checkpoint(
        self,
        checkpoint: KnowledgeExtractionPhaseCheckpoint,
    ) -> None:
        self.saved_checkpoints.append(checkpoint)


class FakeCommandLog(KnowledgeExtractionCommandLogPort):
    def __init__(self) -> None:
        self.commands: list[KnowledgeExtractionCommandRecord] = []

    async def command_exists(self, command_key: str) -> bool:
        return False

    async def record_command(
        self,
        command: KnowledgeExtractionCommandRecord,
    ) -> None:
        self.commands.append(command)


class FakeEventCursor(KnowledgeExtractionEventCursorPort):
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


class FakeCommandEmitter(KnowledgeExtractionCommandEmitterPort):
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
            },
        )


class FakeSourceManagementRepository(SourceManagementRepositoryPort):
    def __init__(
        self,
        *,
        document: SourceDocument | None,
        units: tuple[SourceUnit, ...],
    ) -> None:
        self.document = document
        self.units = units
        self.list_calls = 0

    async def save_source_document(self, document: SourceDocument) -> None:
        self.document = document

    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None:
        return self.document

    async def save_source_units(
        self,
        units: tuple[SourceUnit, ...],
    ) -> None:
        self.units = units

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        self.list_calls += 1
        return self.units

    async def load_source_unit(
        self,
        unit_ref: SourceUnitRef,
    ) -> SourceUnit | None:
        for unit in self.units:
            if unit.unit_ref == unit_ref:
                return unit
        return None


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _later() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _state(
    *,
    status: KnowledgeExtractionWorkflowStatus = KnowledgeExtractionWorkflowStatus.RUNNING,
    current_phase: KnowledgeExtractionPhaseKey = (
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    ),
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id=_workflow_run_id(),
        project_id="project-1",
        source_document_ref=_document_ref().value,
        status=status,
        current_phase=current_phase,
        created_at=_now(),
        updated_at=_now(),
    )


def _source_document() -> SourceDocument:
    return SourceDocument(
        document_ref=_document_ref(),
        project_id="project-1",
        source_format=SourceFormat.MARKDOWN,
        content_hash="content-hash-1",
        created_at=_now(),
        original_filename="source.md",
    )


def _source_unit(*, unit_ref: str, ordinal: int) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(unit_ref),
        document_ref=_document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText(f"# Unit {ordinal}\n\nBody"),
        heading_path=HeadingPath((f"Unit {ordinal}",)),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
        created_at=_now(),
    )


def _source_units() -> tuple[SourceUnit, ...]:
    return (
        _source_unit(unit_ref="source-document:project-1:abc.unit.1", ordinal=1),
        _source_unit(unit_ref="source-document:project-1:abc.unit.0", ordinal=0),
    )


def _scheduling_phase(
    unit_of_work: WorkItemSchedulingUnitOfWorkPort,
) -> AdvanceToDraftObservationSchedulingPhase:
    return AdvanceToDraftObservationSchedulingPhase(
        scheduling_service=ScheduleDraftObservationExtractionWork(
            scheduling_unit_of_work=unit_of_work,
        ),
    )


def _saga(
    *,
    state_repository: FakeStateRepository,
    source_management_repository: SourceManagementRepositoryPort | None = None,
    source_phase_reconciler: KnowledgeExtractionSourcePhaseReconciler | None = None,
    draft_observation_scheduling_phase: (
        AdvanceToDraftObservationSchedulingPhase | None
    ) = None,
) -> KnowledgeExtractionSaga:
    return KnowledgeExtractionSaga(
        state_repository=state_repository,
        command_log=FakeCommandLog(),
        event_cursor=FakeEventCursor(),
        command_emitter=FakeCommandEmitter(),
        source_phase_reconciler=source_phase_reconciler,
        source_management_repository=source_management_repository,
        draft_observation_scheduling_phase=draft_observation_scheduling_phase,
    )


def _command() -> ReconcileKnowledgeExtractionSagaCommand:
    return ReconcileKnowledgeExtractionSagaCommand(
        workflow_run_id=_workflow_run_id(),
        occurred_at=_later(),
    )


def _work_item_id(*, unit_ref: str) -> str:
    return (
        "knowledge-workbench:draft-observation-extraction:"
        f"{_workflow_run_id()}:{unit_ref}"
    )


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.draft_observation_extraction")


@pytest.mark.asyncio
async def test_reconcile_advances_from_source_units_created_to_prompt_work_scheduled() -> (
    None
):
    state_repository = FakeStateRepository(_state())
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=_source_units(),
    )
    scheduling_unit_of_work = FakeWorkItemSchedulingUnitOfWork()

    result = await _saga(
        state_repository=state_repository,
        source_management_repository=source_repository,
        draft_observation_scheduling_phase=_scheduling_phase(scheduling_unit_of_work),
    ).reconcile(_command())

    assert result.current_phase is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    assert result.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert any(
        checkpoint.phase_key is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
        for checkpoint in state_repository.saved_checkpoints
    )
    assert state_repository.saved_states[-1].current_phase is (
        KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    )
    assert len(scheduling_unit_of_work.saved) == 2


@pytest.mark.asyncio
async def test_repeated_reconcile_does_not_duplicate_work_items() -> None:
    state_repository = FakeStateRepository(_state())
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=_source_units(),
    )
    scheduling_unit_of_work = FakeWorkItemSchedulingUnitOfWork()
    saga = _saga(
        state_repository=state_repository,
        source_management_repository=source_repository,
        draft_observation_scheduling_phase=_scheduling_phase(scheduling_unit_of_work),
    )

    first = await saga.reconcile(_command())
    state_repository.state = _state()
    second = await saga.reconcile(_command())

    assert first.current_phase is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    assert second.current_phase is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    assert len(scheduling_unit_of_work.saved) == 2


@pytest.mark.asyncio
async def test_missing_optional_scheduling_dependencies_keeps_source_units_created() -> (
    None
):
    state_repository = FakeStateRepository(_state())

    result = await _saga(state_repository=state_repository).reconcile(_command())

    assert result.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert result.current_phase is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert state_repository.saved_checkpoints == []
    assert state_repository.saved_states == []


@pytest.mark.asyncio
async def test_does_not_schedule_when_source_reconciliation_pauses_workflow() -> None:
    state_repository = FakeStateRepository(
        _state(current_phase=KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED),
    )
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=(),
    )
    scheduling_unit_of_work = FakeWorkItemSchedulingUnitOfWork()

    result = await _saga(
        state_repository=state_repository,
        source_management_repository=source_repository,
        source_phase_reconciler=KnowledgeExtractionSourcePhaseReconciler(
            source_repository=source_repository,
        ),
        draft_observation_scheduling_phase=_scheduling_phase(scheduling_unit_of_work),
    ).reconcile(_command())

    assert result.status is KnowledgeExtractionWorkflowStatus.PAUSED
    assert result.current_phase is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert source_repository.list_calls == 1
    assert scheduling_unit_of_work.saved == []


@pytest.mark.asyncio
async def test_scheduling_conflict_propagates() -> None:
    unit_ref = "source-document:project-1:abc.unit.0"
    work_item_id = _work_item_id(unit_ref=unit_ref)
    state_repository = FakeStateRepository(_state())
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=(_source_unit(unit_ref=unit_ref, ordinal=0),),
    )
    scheduling_unit_of_work = FakeWorkItemSchedulingUnitOfWork(
        existing_items={
            work_item_id: WorkItem(
                work_item_id=work_item_id,
                work_kind=_work_kind(),
            ),
        },
        schedule_payload_hashes={work_item_id: "different-payload-hash"},
    )

    with pytest.raises(ValueError, match="draft observation scheduling conflict"):
        await _saga(
            state_repository=state_repository,
            source_management_repository=source_repository,
            draft_observation_scheduling_phase=_scheduling_phase(
                scheduling_unit_of_work,
            ),
        ).reconcile(_command())


def test_knowledge_extraction_saga_scheduling_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "knowledge_extraction_saga.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "AdvanceToDraftObservationSchedulingPhase",
        "AdvanceToDraftObservationSchedulingPhaseCommand",
        "SourceManagementRepositoryPort",
        "list_source_units_for_document",
        "PROMPT_A_WORK_SCHEDULED",
        "SOURCE_UNITS_CREATED",
    )
    forbidden_markers = (
        _marker("DraftObservationExtraction", "SchedulingReconciler"),
        _marker("DraftObservationExtraction", "WorkIndexPort"),
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "execution_runtime.infrastructure",
        "Postgres",
        "asyncpg",
        "queue",
        "worker",
        "lease",
        "Groq",
        "qwen",
    )

    missing = [marker for marker in required_markers if marker not in source]
    offenders = [marker for marker in forbidden_markers if marker in source]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)


def _marker(*parts: str) -> str:
    return "".join(parts)
