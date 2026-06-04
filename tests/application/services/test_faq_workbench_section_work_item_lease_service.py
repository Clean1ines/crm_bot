from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_section_work_item_lease_service import (
    ClaimSectionWorkItemCommand,
    FaqWorkbenchSectionWorkItemLeaseService,
)
from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
    mark_section_batch_item_leased,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class InMemorySectionWorkItemLeaseRepository:
    items: list[SectionBatchQueueItem] = field(default_factory=list)
    restored_stale_lease_count: int = 0
    restore_calls: list[dict[str, object]] = field(default_factory=list)
    lease_calls: list[dict[str, object]] = field(default_factory=list)

    async def restore_stale_section_work_item_leases(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        now: datetime,
    ) -> int:
        self.restore_calls.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "processing_run_id": processing_run_id,
                "now": now,
            }
        )
        return self.restored_stale_lease_count

    async def lease_next_ready_section_work_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> SectionBatchQueueItem | None:
        self.lease_calls.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "processing_run_id": processing_run_id,
                "worker_id": worker_id,
                "lease_expires_at": lease_expires_at,
                "now": now,
            }
        )

        for index, item in enumerate(self.items):
            if (
                item.project_id == project_id
                and item.document_id == document_id
                and item.processing_run_id == processing_run_id
                and item.status is SectionBatchQueueItemStatus.READY
            ):
                leased = mark_section_batch_item_leased(
                    queue_item=item,
                    worker_id=worker_id,
                    lease_expires_at=lease_expires_at,
                    updated_at=now,
                )
                self.items[index] = leased
                return leased

        return None


def _item(
    *,
    queue_item_id: str = "section-batch-item-1",
    status: SectionBatchQueueItemStatus = SectionBatchQueueItemStatus.READY,
    claim_observations_node_run_id: str | None = None,
    registry_application_queue_item_id: str | None = None,
) -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id=queue_item_id,
        batch_plan_id="batch-plan-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        section_key="intro",
        section_index=0,
        lane_id="section-lane-1",
        lane_index=0,
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=status,
        claim_observations_node_run_id=claim_observations_node_run_id,
        registry_application_queue_item_id=registry_application_queue_item_id,
    )


@pytest.mark.asyncio
async def test_claim_next_ready_section_work_item_restores_stale_leases_before_claim() -> (
    None
):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    repository = InMemorySectionWorkItemLeaseRepository(
        items=[_item()],
        restored_stale_lease_count=2,
    )
    service = FaqWorkbenchSectionWorkItemLeaseService(
        repository=repository,
        time_provider=FixedTimeProvider(now),
    )

    result = await service.claim_next_ready_section_work_item(
        ClaimSectionWorkItemCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
            lease_seconds=120,
        )
    )

    assert result.claimed is True
    assert result.restored_stale_lease_count == 2
    assert result.leased_item is not None
    assert result.leased_item.status is SectionBatchQueueItemStatus.LEASED
    assert result.leased_item.claimed_by_worker_id == "worker-1"
    assert result.leased_item.lease_expires_at == datetime(
        2026, 6, 1, 12, 2, tzinfo=timezone.utc
    )
    assert result.leased_item.attempt_count == 1

    assert len(repository.restore_calls) == 1
    assert len(repository.lease_calls) == 1
    assert repository.restore_calls[0]["now"] == now
    assert repository.lease_calls[0]["lease_expires_at"] == datetime(
        2026, 6, 1, 12, 2, tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_claim_next_ready_section_work_item_returns_none_when_no_ready_item() -> (
    None
):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    repository = InMemorySectionWorkItemLeaseRepository(
        items=[
            _item(
                queue_item_id="section-batch-item-1",
                status=SectionBatchQueueItemStatus.REGISTRY_APPLICATION_APPLIED,
                claim_observations_node_run_id="claim-observations-node-run-1",
                registry_application_queue_item_id="registry-application-item-1",
            )
        ],
    )
    service = FaqWorkbenchSectionWorkItemLeaseService(
        repository=repository,
        time_provider=FixedTimeProvider(now),
    )

    result = await service.claim_next_ready_section_work_item(
        ClaimSectionWorkItemCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
        )
    )

    assert result.claimed is False
    assert result.leased_item is None
    assert len(repository.restore_calls) == 1
    assert len(repository.lease_calls) == 1


def test_claim_command_rejects_blank_worker_id() -> None:
    with pytest.raises(DomainInvariantError, match="worker_id"):
        ClaimSectionWorkItemCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="",
        )


def test_claim_command_rejects_non_positive_lease_seconds() -> None:
    with pytest.raises(DomainInvariantError, match="lease_seconds"):
        ClaimSectionWorkItemCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
            lease_seconds=0,
        )


@pytest.mark.asyncio
async def test_claim_next_ready_section_work_item_does_not_reclaim_registry_application_queued_item() -> (
    None
):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    queued_item = _item(
        queue_item_id="section-batch-item-queued",
        status=SectionBatchQueueItemStatus.REGISTRY_APPLICATION_QUEUED,
        claim_observations_node_run_id="claim-observations-node-run-1",
        registry_application_queue_item_id="registry-application-item-1",
    )
    repository = InMemorySectionWorkItemLeaseRepository(items=[queued_item])
    service = FaqWorkbenchSectionWorkItemLeaseService(
        repository=repository,
        time_provider=FixedTimeProvider(now),
    )

    result = await service.claim_next_ready_section_work_item(
        ClaimSectionWorkItemCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
        )
    )

    assert result.claimed is False
    assert result.leased_item is None
    assert repository.items == [queued_item]
    assert len(repository.restore_calls) == 1
    assert len(repository.lease_calls) == 1
