from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

import pytest

from src.application.services.faq_workbench_section_batch_planning_service import (
    FaqWorkbenchSectionBatchPlanningService,
    ProcessParallelSectionBatchCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
    DomainInvariantError,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    RegistrySnapshot,
    WorkbenchSectionBatchPlan,
    WorkbenchSectionBatchPlanStatus,
    WorkbenchSectionWorkItem,
    WorkbenchSectionWorkItemStatus,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class MonotonicIdFactory:
    current: int = 0

    def new_id(self, prefix: str) -> str:
        self.current += 1
        return f"{prefix}-{self.current}"


@dataclass(slots=True)
class InMemorySectionBatchPlanningRepository:
    node_runs: list[ProcessingNodeRun] = field(default_factory=list)
    artifacts: list[ProcessingNodeArtifact] = field(default_factory=list)
    plans: list[WorkbenchSectionBatchPlan] = field(default_factory=list)
    created_items: list[WorkbenchSectionWorkItem] = field(default_factory=list)
    updated_items: list[WorkbenchSectionWorkItem] = field(default_factory=list)

    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None:
        self.node_runs.append(node_run)

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None:
        self.artifacts.append(artifact)

    async def create_section_batch_plan(
        self,
        plan: WorkbenchSectionBatchPlan,
    ) -> None:
        self.plans.append(plan)

    async def create_section_work_items(
        self,
        items: tuple[WorkbenchSectionWorkItem, ...],
    ) -> None:
        self.created_items.extend(items)

    async def update_section_work_items(
        self,
        items: tuple[WorkbenchSectionWorkItem, ...],
    ) -> None:
        self.updated_items.extend(items)


def _section(index: int) -> DocumentSection:
    return DocumentSection(
        section_id=f"section-{index}",
        document_id="document-1",
        project_id="project-1",
        section_index=index,
        section_key=f"s{index}",
        heading_path=(f"Section {index}",),
        title=f"Section {index}",
        raw_text=f"Raw section {index}",
        normalized_text=f"Normalized section {index}",
        source_refs=(f"document-1#section-{index}",),
        source_chunk_indexes=(index,),
        parent_section_id=None,
        status=DocumentSectionStatus.PENDING,
        metadata={},
    )


def _snapshot(snapshot_id: str = "snapshot-1", sequence: int = 1) -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id=snapshot_id,
        registry_id="registry-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        after_node_run_id="node-run-previous",
        sequence_number=sequence,
        entries_payload={"entries": []},
        relations_payload={"relations": []},
        entry_count=0,
        relation_count=0,
        claim_observation_count=0,
        update_count=0,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _existing_plan() -> WorkbenchSectionBatchPlan:
    return WorkbenchSectionBatchPlan(
        batch_plan_id="batch-plan-existing",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        base_snapshot_id="snapshot-1",
        base_snapshot_sequence_number=1,
        max_concurrency=3,
        status=WorkbenchSectionBatchPlanStatus.RUNNING,
    )


def _existing_item(
    section_id: str,
    *,
    status: WorkbenchSectionWorkItemStatus,
    locked_until: datetime | None = None,
    applied_snapshot_id: str | None = None,
) -> WorkbenchSectionWorkItem:
    return WorkbenchSectionWorkItem(
        work_item_id=f"work-item-{section_id}",
        batch_plan_id="batch-plan-existing",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id=section_id,
        section_index=int(section_id.rsplit("-", 1)[-1]),
        lane_id="lane-1",
        status=status,
        idempotency_key=f"idem-{section_id}",
        based_on_snapshot_id="snapshot-1",
        based_on_snapshot_sequence_number=1,
        locked_by="worker-1" if locked_until is not None else None,
        locked_until=locked_until,
        applied_snapshot_id=applied_snapshot_id,
    )


@pytest.mark.asyncio
async def test_process_parallel_section_batch_creates_persisted_work_plan_for_three_lanes() -> (
    None
):
    repository = InMemorySectionBatchPlanningRepository()
    service = FaqWorkbenchSectionBatchPlanningService(
        repository,
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )

    result = await service.process_parallel_section_batch(
        ProcessParallelSectionBatchCommand(
            sections=tuple(_section(index) for index in range(6)),
            latest_registry_snapshot=_snapshot(),
            max_concurrency=3,
        )
    )

    assert (
        result.node_run.node_name is ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH
    )
    assert result.node_run.node_kind.value == "control_flow"
    assert result.node_run.status is ProcessingNodeStatus.COMPLETED
    assert (
        result.input_artifact.artifact_type is ProcessingNodeArtifactType.INPUT_SNAPSHOT
    )
    assert (
        result.output_artifact.artifact_type
        is ProcessingNodeArtifactType.DETERMINISTIC_RESULT
    )

    assert result.batch_plan.max_concurrency == 3
    assert result.batch_plan.base_snapshot_id == "snapshot-1"
    assert tuple(item.section_id for item in result.work_items) == (
        "section-0",
        "section-1",
        "section-2",
        "section-3",
        "section-4",
        "section-5",
    )
    assert tuple(item.lane_id for item in result.work_items) == (
        "lane-1",
        "lane-1",
        "lane-2",
        "lane-2",
        "lane-3",
        "lane-3",
    )
    assert all(item.based_on_snapshot_id == "snapshot-1" for item in result.work_items)
    assert all(item.idempotency_key for item in result.work_items)

    assert repository.node_runs == [result.node_run]
    assert repository.artifacts == [result.input_artifact, result.output_artifact]
    assert repository.plans == [result.batch_plan]
    assert repository.created_items == list(result.work_items)
    assert repository.updated_items == []
    assert result.runnable_section_ids == (
        "section-0",
        "section-1",
        "section-2",
        "section-3",
        "section-4",
        "section-5",
    )


@pytest.mark.asyncio
async def test_process_parallel_section_batch_restores_stale_leases_without_recreating_applied_items() -> (
    None
):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    repository = InMemorySectionBatchPlanningRepository()
    service = FaqWorkbenchSectionBatchPlanningService(
        repository,
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(now),
    )
    stale = _existing_item(
        "section-0",
        status=WorkbenchSectionWorkItemStatus.FINDINGS_RUNNING,
        locked_until=now - timedelta(minutes=10),
    )
    applied = _existing_item(
        "section-1",
        status=WorkbenchSectionWorkItemStatus.APPLIED,
        applied_snapshot_id="snapshot-2",
    )

    result = await service.process_parallel_section_batch(
        ProcessParallelSectionBatchCommand(
            sections=(_section(0), _section(1)),
            latest_registry_snapshot=_snapshot(snapshot_id="snapshot-2", sequence=2),
            max_concurrency=3,
            existing_plan=_existing_plan(),
            existing_work_items=(stale, applied),
        )
    )

    assert result.work_items[0].status is WorkbenchSectionWorkItemStatus.PENDING
    assert result.work_items[0].locked_by is None
    assert result.work_items[1] is applied
    assert result.runnable_section_ids == ("section-0",)

    assert repository.plans == []
    assert repository.created_items == []
    assert repository.updated_items == list(result.work_items)


@pytest.mark.asyncio
async def test_process_parallel_section_batch_rejects_duplicate_sections_before_persisting() -> (
    None
):
    repository = InMemorySectionBatchPlanningRepository()
    service = FaqWorkbenchSectionBatchPlanningService(
        repository,
        id_factory=MonotonicIdFactory(),
    )

    duplicated = replace(_section(1), section_index=2)

    with pytest.raises(DomainInvariantError, match="duplicate section"):
        await service.process_parallel_section_batch(
            ProcessParallelSectionBatchCommand(
                sections=(_section(1), duplicated),
                latest_registry_snapshot=_snapshot(),
            )
        )

    assert repository.node_runs == []
    assert repository.plans == []
    assert repository.created_items == []
