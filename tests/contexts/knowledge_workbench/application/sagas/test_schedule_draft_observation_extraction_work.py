from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    work_item_schedule_payload_hash,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.schedule_draft_observation_extraction_work import (
    ScheduleDraftObservationExtractionWork,
    ScheduleDraftObservationExtractionWorkCommand,
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


def _document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _source_unit(*, unit_ref: str, ordinal: int) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(unit_ref),
        document_ref=_document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText(f"# Unit {ordinal}\\n\\nBody"),
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


def _command(
    *,
    source_units: tuple[SourceUnit, ...] | None = None,
    workflow_run_id: str = "knowledge-extraction:source-document:project-1:abc",
) -> ScheduleDraftObservationExtractionWorkCommand:
    return ScheduleDraftObservationExtractionWorkCommand(
        workflow_run_id=workflow_run_id,
        source_document_ref=_document_ref(),
        source_units=_source_units() if source_units is None else source_units,
    )


def _service(
    unit_of_work: WorkItemSchedulingRepositoryPort,
) -> ScheduleDraftObservationExtractionWork:
    return ScheduleDraftObservationExtractionWork(
        scheduling_repository=unit_of_work,
    )


def _work_item_id(*, workflow_run_id: str, unit_ref: str) -> str:
    return (
        f"knowledge-workbench:draft-observation-extraction:{workflow_run_id}:{unit_ref}"
    )


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.draft_observation_extraction")


def _expected_payload(
    *, workflow_run_id: str, unit_ref: str, ordinal: int
) -> dict[str, object]:
    return {
        "workflow_run_id": workflow_run_id,
        "source_document_ref": _document_ref().value,
        "source_unit_ref": unit_ref,
        "source_unit_ordinal": ordinal,
        "phase": "draft_observation_extraction",
        "provider_messages": (
            {
                "role": "system",
                "content": (
                    "Extract draft claim observations as strict JSON. "
                    "Use prompt_id faq_claim_observations and return only JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"source_unit_ref: {unit_ref}\n"
                    f"heading_path: Unit {ordinal}\n\n"
                    f"# Unit {ordinal}\n\nBody"
                ),
            },
        ),
        "prompt_a_provenance": {
            "workflow_run_id": workflow_run_id,
            "stage_run_id": "draft_observation_extraction",
            "source_unit_ref": unit_ref,
            "work_item_id": _work_item_id(
                workflow_run_id=workflow_run_id,
                unit_ref=unit_ref,
            ),
            "prompt_id": "faq_claim_observations",
            "prompt_version": "v1",
        },
    }


@pytest.mark.asyncio
async def test_schedules_created_work_items_for_source_units() -> None:
    unit_of_work = FakeWorkItemSchedulingRepository()

    result = await _service(unit_of_work).execute(_command())

    assert result.planned_count == 2
    assert result.created_count == 2
    assert result.already_exists_count == 0
    assert result.conflict_count == 0
    assert result.is_conflict_free
    assert len(result.scheduled_items) == 2
    assert len(unit_of_work.saved) == 2

    first_item = result.scheduled_items[0]
    first_payload = unit_of_work.saved[0].payload
    assert first_payload["workflow_run_id"] == (
        "knowledge-extraction:source-document:project-1:abc"
    )
    assert first_payload["source_document_ref"] == _document_ref().value
    assert first_payload["source_unit_ref"] == "source-document:project-1:abc.unit.0"
    assert first_payload["source_unit_ordinal"] == 0
    assert first_payload["phase"] == "draft_observation_extraction"
    assert "provider_messages" in first_payload
    assert "prompt_a_provenance" in first_payload

    first_provenance = first_payload["prompt_a_provenance"]
    assert isinstance(first_provenance, Mapping)
    assert first_provenance["workflow_run_id"] == (
        "knowledge-extraction:source-document:project-1:abc"
    )
    assert first_provenance["source_unit_ref"] == (
        "source-document:project-1:abc.unit.0"
    )
    assert first_provenance["work_item_id"] == _work_item_id(
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        unit_ref="source-document:project-1:abc.unit.0",
    )
    assert first_provenance["prompt_id"] == "faq_claim_observations"
    assert first_provenance["prompt_version"] == "v1"

    assert "work_item_attempt_id" not in first_payload
    assert "llm_task_id" not in first_payload
    assert "llm_attempt_id" not in first_payload
    assert "work_item_attempt_id" not in first_provenance
    assert "llm_task_id" not in first_provenance
    assert "llm_attempt_id" not in first_provenance

    assert first_item.source_unit_ref == "source-document:project-1:abc.unit.0"
    assert first_item.source_unit_ordinal == 0
    assert first_item.work_item_id == _work_item_id(
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        unit_ref="source-document:project-1:abc.unit.0",
    )
    assert first_item.work_kind == "knowledge_workbench.draft_observation_extraction"
    assert first_item.idempotency_key == first_item.work_item_id
    assert first_item.payload_hash == work_item_schedule_payload_hash(first_payload)
    assert first_item.schedule_status == "created"

    saved_ids = tuple(saved.item.work_item_id for saved in unit_of_work.saved)
    assert saved_ids == (
        _work_item_id(
            workflow_run_id="knowledge-extraction:source-document:project-1:abc",
            unit_ref="source-document:project-1:abc.unit.0",
        ),
        _work_item_id(
            workflow_run_id="knowledge-extraction:source-document:project-1:abc",
            unit_ref="source-document:project-1:abc.unit.1",
        ),
    )
    assert tuple(saved.payload["source_unit_ref"] for saved in unit_of_work.saved) == (
        "source-document:project-1:abc.unit.0",
        "source-document:project-1:abc.unit.1",
    )
    assert all("provider_messages" in saved.payload for saved in unit_of_work.saved)
    assert all("prompt_a_provenance" in saved.payload for saved in unit_of_work.saved)
    assert (
        "# Unit 0\\n\\nBody"
        in unit_of_work.saved[0].payload["provider_messages"][1]["content"]
    )
    assert unit_of_work.saved[0].payload["prompt_a_provenance"]["prompt_id"] == (
        "faq_claim_observations"
    )


@pytest.mark.asyncio
async def test_repeated_execution_is_already_exists() -> None:
    unit_of_work = FakeWorkItemSchedulingRepository()
    service = _service(unit_of_work)

    first = await service.execute(_command())
    second = await service.execute(_command())

    assert first.created_count == 2
    assert second.planned_count == 2
    assert second.created_count == 0
    assert second.already_exists_count == 2
    assert second.conflict_count == 0
    assert len(unit_of_work.saved) == 2
    assert tuple(item.schedule_status for item in second.scheduled_items) == (
        "already_exists",
        "already_exists",
    )
    assert tuple(item.work_item_id for item in second.scheduled_items) == tuple(
        item.work_item_id for item in first.scheduled_items
    )
    assert tuple(item.payload_hash for item in second.scheduled_items) == tuple(
        item.payload_hash for item in first.scheduled_items
    )


@pytest.mark.asyncio
async def test_conflict_is_surfaced() -> None:
    workflow_run_id = "knowledge-extraction:source-document:project-1:abc"
    unit_ref = "source-document:project-1:abc.unit.0"
    work_item_id = _work_item_id(
        workflow_run_id=workflow_run_id,
        unit_ref=unit_ref,
    )
    unit_of_work = FakeWorkItemSchedulingRepository(
        existing_items={
            work_item_id: WorkItem(
                work_item_id=work_item_id,
                work_kind=_work_kind(),
            ),
        },
        schedule_payload_hashes={work_item_id: "different-payload-hash"},
    )

    result = await _service(unit_of_work).execute(
        _command(source_units=(_source_unit(unit_ref=unit_ref, ordinal=0),)),
    )

    assert result.planned_count == 1
    assert result.created_count == 0
    assert result.already_exists_count == 0
    assert result.conflict_count == 1
    assert result.is_conflict_free is False
    assert len(result.scheduled_items) == 1
    assert result.scheduled_items[0].schedule_status == "conflict"
    assert result.scheduled_items[0].source_unit_ref == unit_ref
    assert result.scheduled_items[0].work_item_id == work_item_id
    assert unit_of_work.saved == []


@pytest.mark.asyncio
async def test_empty_source_units_is_safe_no_op() -> None:
    unit_of_work = FakeWorkItemSchedulingRepository()

    result = await _service(unit_of_work).execute(_command(source_units=()))

    assert result.planned_count == 0
    assert result.created_count == 0
    assert result.already_exists_count == 0
    assert result.conflict_count == 0
    assert result.scheduled_items == ()
    assert result.is_conflict_free
    assert unit_of_work.saved == []


@pytest.mark.asyncio
async def test_invalid_command_is_rejected() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        _command(workflow_run_id="  ")

    with pytest.raises(TypeError, match="source_units must be tuple"):
        ScheduleDraftObservationExtractionWorkCommand(
            workflow_run_id="run-1",
            source_document_ref=_document_ref(),
            source_units=cast(tuple[SourceUnit, ...], []),
        )


@pytest.mark.asyncio
async def test_repeated_execution_uses_same_payload_hashes() -> None:
    unit_of_work = FakeWorkItemSchedulingRepository()
    service = _service(unit_of_work)

    await service.execute(_command())
    first_hashes = dict(unit_of_work.schedule_payload_hashes)
    await service.execute(_command())

    assert first_hashes == unit_of_work.schedule_payload_hashes
    for saved in unit_of_work.saved:
        assert saved.payload_hash == work_item_schedule_payload_hash(saved.payload)


@pytest.mark.asyncio
async def test_schedule_draft_observation_extraction_work_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "schedule_draft_observation_extraction_work.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "ScheduleDraftObservationExtractionWork",
        "ScheduleDraftObservationExtractionWorkCommand",
        "ScheduleDraftObservationExtractionWorkResult",
        "PlanDraftObservationExtractionWork",
        "MapDraftObservationPlansToExecutionSchedule",
        "EnsureWorkItemsScheduled",
        "WorkItemSchedulingRepositoryPort",
        "created_count",
        "already_exists_count",
        "conflict_count",
        "DraftObservationScheduledWorkItemSummary",
        "scheduled_items",
        "payload_hash",
        "schedule_status",
        "work_item_schedule_payload_hash",
    )
    forbidden_markers = (
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
        "Prompt",
        "LLM",
    )

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source


def test_schedule_draft_observation_service_uses_repository_without_transaction_ownership() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "schedule_draft_observation_extraction_work.py",
    ).read_text(encoding="utf-8")

    assert "scheduling_repository: WorkItemSchedulingRepositoryPort" in source
    assert "scheduling_unit_of_work" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
