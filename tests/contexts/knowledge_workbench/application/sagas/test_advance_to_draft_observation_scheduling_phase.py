from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    work_item_schedule_payload_hash,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.advance_to_draft_observation_scheduling_phase import (
    AdvanceToDraftObservationSchedulingPhase,
    AdvanceToDraftObservationSchedulingPhaseCommand,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.schedule_draft_observation_extraction_work import (
    ScheduleDraftObservationExtractionWork,
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
class FakeWorkItemSchedulingRepository:
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


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _later() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _state(
    *,
    current_phase: KnowledgeExtractionPhaseKey = (
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    ),
    status: KnowledgeExtractionWorkflowStatus = KnowledgeExtractionWorkflowStatus.RUNNING,
    checkpoints: tuple[KnowledgeExtractionPhaseCheckpoint, ...] = (),
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id=_workflow_run_id(),
        project_id="project-1",
        source_document_ref=_document_ref().value,
        status=status,
        current_phase=current_phase,
        checkpoints=checkpoints,
        pause_reason="manual-pause"
        if status is KnowledgeExtractionWorkflowStatus.PAUSED
        else None,
        created_at=_now(),
        updated_at=_now(),
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


def _service(
    unit_of_work: WorkItemSchedulingRepositoryPort,
) -> AdvanceToDraftObservationSchedulingPhase:
    return AdvanceToDraftObservationSchedulingPhase(
        scheduling_service=ScheduleDraftObservationExtractionWork(
            scheduling_repository=unit_of_work,
        ),
    )


def _command(
    *,
    state: KnowledgeExtractionWorkflowState | None = None,
    source_units: tuple[SourceUnit, ...] | None = None,
) -> AdvanceToDraftObservationSchedulingPhaseCommand:
    return AdvanceToDraftObservationSchedulingPhaseCommand(
        state=_state() if state is None else state,
        source_units=_source_units() if source_units is None else source_units,
        occurred_at=_later(),
    )


def _work_item_id(*, unit_ref: str) -> str:
    return (
        "knowledge-workbench:draft-observation-extraction:"
        f"{_workflow_run_id()}:{unit_ref}"
    )


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.draft_observation_extraction")


def _expected_payload(*, unit_ref: str, ordinal: int) -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": _document_ref().value,
        "source_unit_ref": unit_ref,
        "source_unit_ordinal": ordinal,
        "phase": "draft_observation_extraction",
    }


@pytest.mark.asyncio
async def test_advances_phase_after_scheduling_created_work() -> None:
    unit_of_work = FakeWorkItemSchedulingRepository()

    result = await _service(unit_of_work).execute(_command())

    assert (
        result.state.current_phase
        is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    )
    assert result.state.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert (
        result.checkpoint.phase_key
        is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    )
    assert result.checkpoint.phase_status is KnowledgeExtractionPhaseStatus.COMPLETED
    assert result.checkpoint.expected_count == 2
    assert result.checkpoint.completed_count == 2
    assert result.planned_count == 2
    assert result.created_count == 2
    assert result.already_exists_count == 0
    assert result.conflict_count == 0
    payload = result.checkpoint.checkpoint_payload
    assert payload["created_count"] == 2
    assert payload["already_exists_count"] == 0
    assert payload["scheduler"] == "execution_runtime.ensure_work_items_scheduled"
    assert payload["schedule_schema_version"] == 1
    scheduled_items = payload["scheduled_items"]
    assert isinstance(scheduled_items, list)
    assert len(scheduled_items) == 2

    first_item = scheduled_items[0]
    assert first_item["source_unit_ref"] == "source-document:project-1:abc.unit.0"
    assert first_item["source_unit_ordinal"] == 0
    assert first_item["work_item_id"] == _work_item_id(
        unit_ref="source-document:project-1:abc.unit.0",
    )
    assert first_item["work_kind"] == "knowledge_workbench.draft_observation_extraction"
    assert first_item["idempotency_key"] == first_item["work_item_id"]
    assert first_item["payload_hash"] == work_item_schedule_payload_hash(
        _expected_payload(
            unit_ref="source-document:project-1:abc.unit.0",
            ordinal=0,
        ),
    )
    assert first_item["schedule_status"] == "created"


@pytest.mark.asyncio
async def test_repeated_execution_uses_already_exists_and_still_advances() -> None:
    unit_of_work = FakeWorkItemSchedulingRepository()
    service = _service(unit_of_work)
    original_state = _state()

    first = await service.execute(_command(state=original_state))
    second = await service.execute(_command(state=original_state))

    assert first.created_count == 2
    assert second.planned_count == 2
    assert second.created_count == 0
    assert second.already_exists_count == 2
    assert second.conflict_count == 0
    assert second.checkpoint.completed_count == 2
    scheduled_items = second.checkpoint.checkpoint_payload["scheduled_items"]
    assert isinstance(scheduled_items, list)
    assert len(scheduled_items) == 2
    assert tuple(item["schedule_status"] for item in scheduled_items) == (
        "already_exists",
        "already_exists",
    )
    assert (
        second.state.current_phase
        is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    )
    assert len(unit_of_work.saved) == 2


@pytest.mark.asyncio
async def test_conflict_raises_and_does_not_produce_checkpoint() -> None:
    unit_ref = "source-document:project-1:abc.unit.0"
    work_item_id = _work_item_id(unit_ref=unit_ref)
    unit_of_work = FakeWorkItemSchedulingRepository(
        existing_items={
            work_item_id: WorkItem(
                work_item_id=work_item_id,
                work_kind=_work_kind(),
            ),
        },
        schedule_payload_hashes={work_item_id: "different-payload-hash"},
    )

    with pytest.raises(ValueError, match="draft observation scheduling conflict"):
        await _service(unit_of_work).execute(
            _command(source_units=(_source_unit(unit_ref=unit_ref, ordinal=0),)),
        )

    assert unit_of_work.saved == []


@pytest.mark.asyncio
async def test_rejects_wrong_current_phase() -> None:
    with pytest.raises(ValueError, match="current_phase must be SOURCE_UNITS_CREATED"):
        _command(
            state=_state(
                current_phase=KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED,
            ),
        )


@pytest.mark.asyncio
async def test_rejects_non_running_workflow() -> None:
    with pytest.raises(ValueError, match="workflow status must be RUNNING"):
        _command(state=_state(status=KnowledgeExtractionWorkflowStatus.PAUSED))


@pytest.mark.asyncio
async def test_existing_checkpoint_is_replaced_not_duplicated() -> None:
    old_checkpoint = KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id=_workflow_run_id(),
        phase_key=KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        expected_count=1,
        completed_count=1,
        idempotency_key=f"prompt-a-work-scheduled:{_workflow_run_id()}",
        checkpoint_payload={"old": True},
        updated_at=_now(),
    )
    state = _state(checkpoints=(old_checkpoint,))

    result = await _service(FakeWorkItemSchedulingRepository()).execute(
        _command(state=state)
    )

    matching_checkpoints = tuple(
        checkpoint
        for checkpoint in result.state.checkpoints
        if checkpoint.phase_key is KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
    )
    assert len(matching_checkpoints) == 1
    assert matching_checkpoints[0].checkpoint_payload["planned_count"] == 2
    assert "old" not in matching_checkpoints[0].checkpoint_payload


@pytest.mark.asyncio
async def test_advance_to_draft_observation_scheduling_phase_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "advance_to_draft_observation_scheduling_phase.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "AdvanceToDraftObservationSchedulingPhase",
        "AdvanceToDraftObservationSchedulingPhaseCommand",
        "AdvanceToDraftObservationSchedulingPhaseResult",
        "ScheduleDraftObservationExtractionWork",
        "PROMPT_A_WORK_SCHEDULED",
        "execution_runtime.ensure_work_items_scheduled",
        "replace_or_append_checkpoint",
        "schedule_schema_version",
        "scheduled_items",
        "to_checkpoint_payload",
    )
    forbidden_markers = (
        _marker("DraftObservationExtraction", "SchedulingReconciler"),
        _marker("DraftObservationExtraction", "WorkIndexPort"),
        "_replace_or_append_checkpoint",
        "from .knowledge_extraction_saga import _replace_checkpoints",
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

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source


def _marker(*parts: str) -> str:
    return "".join(parts)


def test_advance_to_draft_observation_scheduling_phase_has_no_transaction_ownership() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "advance_to_draft_observation_scheduling_phase.py",
    ).read_text(encoding="utf-8")

    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "scheduling_unit_of_work" not in source
