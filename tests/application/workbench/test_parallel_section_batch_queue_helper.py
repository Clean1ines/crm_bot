from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.application.workbench.helpers import InMemoryWorkbenchRepository
from src.domain.project_plane.knowledge_workbench import (
    ParallelSectionBatchPlan,
    ParallelSectionLane,
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
    mark_section_batch_item_leased,
)


def _item(
    *,
    queue_item_id: str = "section-batch-item-1",
    section_index: int = 0,
    lane_index: int = 0,
) -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id=queue_item_id,
        batch_plan_id="section-batch-plan-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id=f"section-{section_index + 1}",
        section_key=f"section-{section_index + 1}",
        section_index=section_index,
        lane_id=f"section-lane-{lane_index + 1}",
        lane_index=lane_index,
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=SectionBatchQueueItemStatus.READY,
    )


def _plan() -> ParallelSectionBatchPlan:
    items = (
        _item(queue_item_id="section-batch-item-2", section_index=1, lane_index=1),
        _item(queue_item_id="section-batch-item-1", section_index=0, lane_index=0),
    )
    return ParallelSectionBatchPlan(
        batch_plan_id="section-batch-plan-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        max_lanes=2,
        lanes=(
            ParallelSectionLane(
                lane_id="section-lane-1",
                lane_index=0,
                section_ids=("section-1",),
            ),
            ParallelSectionLane(
                lane_id="section-lane-2",
                lane_index=1,
                section_ids=("section-2",),
            ),
        ),
        queue_items=items,
    )


@pytest.mark.asyncio
async def test_inmemory_repository_persists_and_orders_section_batch_queue_items() -> (
    None
):
    repository = InMemoryWorkbenchRepository()

    await repository.create_parallel_section_batch_plan(_plan())

    items = await repository.list_section_batch_queue_items(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert [item.queue_item_id for item in items] == [
        "section-batch-item-1",
        "section-batch-item-2",
    ]
    assert repository.section_batch_plans[0].batch_plan_id == "section-batch-plan-1"


@pytest.mark.asyncio
async def test_inmemory_repository_updates_section_batch_queue_item_checkpoint() -> (
    None
):
    repository = InMemoryWorkbenchRepository()
    await repository.create_parallel_section_batch_plan(_plan())

    item = (
        await repository.list_section_batch_queue_items(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )
    )[0]

    leased = mark_section_batch_item_leased(
        queue_item=item,
        worker_id="worker-1",
        lease_expires_at=datetime(2026, 6, 1, tzinfo=timezone.utc)
        + timedelta(minutes=5),
    )

    await repository.update_section_batch_queue_item(leased)

    items = await repository.list_section_batch_queue_items(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert items[0].status is SectionBatchQueueItemStatus.LEASED
    assert items[0].claimed_by_worker_id == "worker-1"
    assert items[0].attempt_count == 1
