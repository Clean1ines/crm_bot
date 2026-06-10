from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
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
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_reconcile_unit_of_work import (
    KnowledgeExtractionSagaReconcileUnitOfWorkPort,
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
class FakeWorkItemSchedulingRepository(WorkItemSchedulingRepositoryPort):
    existing_items: dict[str, WorkItem] = field(default_factory=dict)
    schedule_payload_hashes: dict[str, str] = field(default_factory=dict)
    saved: list[SavedScheduledWorkItem] = field(default_factory=list)

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        return self.existing_items.get(work_item_id)

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        return self.schedule_payload_hashes.get(work_item_id)

    async def save_scheduled_work_item(
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


class FakeSagaReconcileUnitOfWork(KnowledgeExtractionSagaReconcileUnitOfWorkPort):
    def __init__(
        self,
        *,
        state_repository: FakeStateRepository,
        source_management_repository: SourceManagementRepositoryPort | None = None,
        scheduling_repository: WorkItemSchedulingRepositoryPort | None = None,
        command_log: FakeCommandLog | None = None,
        event_cursor: FakeEventCursor | None = None,
        command_emitter: FakeCommandEmitter | None = None,
    ) -> None:
        self._state_repository = state_repository
        self._command_log = command_log or FakeCommandLog()
        self._event_cursor = event_cursor or FakeEventCursor()
        self._command_emitter = command_emitter or FakeCommandEmitter()
        self._source_management_repository = (
            source_management_repository
            or FakeSourceManagementRepository(document=None, units=())
        )
        self._scheduling_repository = (
            scheduling_repository or FakeWorkItemSchedulingRepository()
        )
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
        return self._scheduling_repository

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


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


def _saga(
    *,
    unit_of_work: KnowledgeExtractionSagaReconcileUnitOfWorkPort,
    source_phase_reconciler: KnowledgeExtractionSourcePhaseReconciler | None = None,
) -> KnowledgeExtractionSaga:
    return KnowledgeExtractionSaga(
        unit_of_work=unit_of_work,
        source_phase_reconciler=source_phase_reconciler,
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
    scheduling_repository = FakeWorkItemSchedulingRepository()
    unit_of_work = FakeSagaReconcileUnitOfWork(
        state_repository=state_repository,
        source_management_repository=source_repository,
        scheduling_repository=scheduling_repository,
    )

    result = await _saga(unit_of_work=unit_of_work).reconcile(_command())

    assert result.current_phase is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    assert result.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 0
    assert any(
        checkpoint.phase_key is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
        for checkpoint in state_repository.saved_checkpoints
    )
    assert state_repository.saved_states[-1].current_phase is (
        KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    )
    assert len(scheduling_repository.saved) == 2
    checkpoint = state_repository.saved_checkpoints[-1]
    scheduled_items = checkpoint.checkpoint_payload["scheduled_items"]
    assert isinstance(scheduled_items, list)
    assert len(scheduled_items) == 2
    assert (
        scheduled_items[0]["source_unit_ref"] == "source-document:project-1:abc.unit.0"
    )
    assert scheduled_items[0]["source_unit_ordinal"] == 0
    assert scheduled_items[0]["work_item_id"] == _work_item_id(
        unit_ref="source-document:project-1:abc.unit.0",
    )
    assert scheduled_items[0]["work_kind"] == (
        "knowledge_workbench.draft_observation_extraction"
    )
    assert scheduled_items[0]["idempotency_key"] == scheduled_items[0]["work_item_id"]
    assert isinstance(scheduled_items[0]["payload_hash"], str)
    assert scheduled_items[0]["payload_hash"]
    assert scheduled_items[0]["schedule_status"] == "created"


@pytest.mark.asyncio
async def test_repeated_reconcile_does_not_duplicate_work_items() -> None:
    state_repository = FakeStateRepository(_state())
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=_source_units(),
    )
    scheduling_repository = FakeWorkItemSchedulingRepository()
    unit_of_work = FakeSagaReconcileUnitOfWork(
        state_repository=state_repository,
        source_management_repository=source_repository,
        scheduling_repository=scheduling_repository,
    )
    saga = _saga(unit_of_work=unit_of_work)

    first = await saga.reconcile(_command())
    state_repository.state = _state()
    second = await saga.reconcile(_command())

    assert first.current_phase is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    assert second.current_phase is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    assert len(scheduling_repository.saved) == 2
    assert unit_of_work.commit_count == 2
    assert unit_of_work.rollback_count == 0


@pytest.mark.asyncio
async def test_empty_source_units_advance_to_prompt_work_scheduled_without_work_items() -> (
    None
):
    state_repository = FakeStateRepository(_state())
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=(),
    )
    scheduling_repository = FakeWorkItemSchedulingRepository()
    unit_of_work = FakeSagaReconcileUnitOfWork(
        state_repository=state_repository,
        source_management_repository=source_repository,
        scheduling_repository=scheduling_repository,
    )

    result = await _saga(unit_of_work=unit_of_work).reconcile(_command())

    assert result.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert result.current_phase is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    assert state_repository.saved_checkpoints
    assert state_repository.saved_states
    assert scheduling_repository.saved == []
    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 0


@pytest.mark.asyncio
async def test_does_not_schedule_when_source_reconciliation_pauses_workflow() -> None:
    state_repository = FakeStateRepository(
        _state(current_phase=KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED),
    )
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=(),
    )
    scheduling_repository = FakeWorkItemSchedulingRepository()
    unit_of_work = FakeSagaReconcileUnitOfWork(
        state_repository=state_repository,
        source_management_repository=source_repository,
        scheduling_repository=scheduling_repository,
    )

    result = await _saga(
        unit_of_work=unit_of_work,
        source_phase_reconciler=KnowledgeExtractionSourcePhaseReconciler(
            source_repository=source_repository,
        ),
    ).reconcile(_command())

    assert result.status is KnowledgeExtractionWorkflowStatus.PAUSED
    assert result.current_phase is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert source_repository.list_calls == 1
    assert scheduling_repository.saved == []
    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 0


@pytest.mark.asyncio
async def test_scheduling_conflict_propagates_and_rolls_back() -> None:
    unit_ref = "source-document:project-1:abc.unit.0"
    work_item_id = _work_item_id(unit_ref=unit_ref)
    state_repository = FakeStateRepository(_state())
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=(_source_unit(unit_ref=unit_ref, ordinal=0),),
    )
    scheduling_repository = FakeWorkItemSchedulingRepository(
        existing_items={
            work_item_id: WorkItem(
                work_item_id=work_item_id,
                work_kind=_work_kind(),
            ),
        },
        schedule_payload_hashes={work_item_id: "different-payload-hash"},
    )
    unit_of_work = FakeSagaReconcileUnitOfWork(
        state_repository=state_repository,
        source_management_repository=source_repository,
        scheduling_repository=scheduling_repository,
    )

    with pytest.raises(ValueError, match="draft observation scheduling conflict"):
        await _saga(unit_of_work=unit_of_work).reconcile(_command())

    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 1


@pytest.mark.asyncio
async def test_knowledge_extraction_saga_rolls_back_on_scheduling_exception() -> None:
    class FailingSchedulingRepository(FakeWorkItemSchedulingRepository):
        async def save_scheduled_work_item(
            self,
            *,
            item: WorkItem,
            idempotency_key: str,
            payload_hash: str,
            payload: Mapping[str, object],
        ) -> None:
            raise RuntimeError("scheduling failed")

    state_repository = FakeStateRepository(_state())
    source_repository = FakeSourceManagementRepository(
        document=_source_document(),
        units=(
            _source_unit(
                unit_ref="source-document:project-1:abc.unit.0",
                ordinal=0,
            ),
        ),
    )
    unit_of_work = FakeSagaReconcileUnitOfWork(
        state_repository=state_repository,
        source_management_repository=source_repository,
        scheduling_repository=FailingSchedulingRepository(),
    )

    with pytest.raises(RuntimeError, match="scheduling failed"):
        await _saga(unit_of_work=unit_of_work).reconcile(_command())

    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 1


def test_knowledge_extraction_saga_scheduling_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "knowledge_extraction_saga.py",
    ).read_text(encoding="utf-8")

    assert "KnowledgeExtractionSagaReconcileUnitOfWorkPort" in source
    assert "unit_of_work: KnowledgeExtractionSagaReconcileUnitOfWorkPort" in source
    assert "self._unit_of_work = unit_of_work" in source
    assert "await self._unit_of_work.commit()" in source
    assert "await self._unit_of_work.rollback()" in source
    assert "ScheduleDraftObservationExtractionWork" in source

    forbidden_old_constructor_markers = (
        "state_repository:",
        "source_management_repository:",
        "draft_observation_scheduling_phase:",
        "scheduling_unit_of_work",
        "WorkItemSchedulingUnitOfWorkPort",
    )
    for marker in forbidden_old_constructor_markers:
        assert marker not in source, marker


def test_knowledge_extraction_saga_single_uow_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "knowledge_extraction_saga.py",
    ).read_text(encoding="utf-8")

    assert "unit_of_work: KnowledgeExtractionSagaReconcileUnitOfWorkPort" in source
    assert "await self._unit_of_work.commit()" in source
    assert "await self._unit_of_work.rollback()" in source
    assert "state_repository:" not in source
    assert "source_management_repository:" not in source
    assert "draft_observation_scheduling_phase:" not in source
