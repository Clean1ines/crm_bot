from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from math import ceil
from typing import Sequence

from .registry import RegistrySnapshot
from .shared import (
    ArtifactId,
    DocumentId,
    DomainInvariantError,
    NodeRunId,
    ProcessingRunId,
    ProjectId,
    SectionId,
    SnapshotId,
    require_document_id,
    require_processing_run_id,
    require_project_id,
)


class WorkbenchSectionBatchPlanStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WorkbenchSectionWorkItemStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    FINDINGS_RUNNING = "findings_running"
    FINDINGS_COMPLETED = "findings_completed"
    DEDUP_COMPLETED = "dedup_completed"
    APPLY_PENDING = "apply_pending"
    REBASING = "rebasing"
    APPLIED = "applied"
    NEEDS_REVISIT = "needs_revisit"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class WorkbenchSectionBatchPlan:
    batch_plan_id: str
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    base_snapshot_id: SnapshotId
    base_snapshot_sequence_number: int
    max_concurrency: int
    status: WorkbenchSectionBatchPlanStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.batch_plan_id:
            raise DomainInvariantError("batch_plan_id is required")
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.base_snapshot_id:
            raise DomainInvariantError("section batch plan requires base_snapshot_id")
        if self.base_snapshot_sequence_number < 1:
            raise DomainInvariantError(
                "section batch plan base snapshot sequence must be positive"
            )
        if self.max_concurrency < 1:
            raise DomainInvariantError("section batch max_concurrency must be positive")


@dataclass(frozen=True, slots=True)
class WorkbenchSectionWorkItem:
    work_item_id: str
    batch_plan_id: str
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    section_id: SectionId
    section_index: int
    lane_id: str
    status: WorkbenchSectionWorkItemStatus
    idempotency_key: str
    based_on_snapshot_id: SnapshotId | None = None
    based_on_snapshot_sequence_number: int | None = None
    findings_node_run_id: NodeRunId | None = None
    dedup_node_run_id: NodeRunId | None = None
    registry_application_node_run_id: NodeRunId | None = None
    parsed_artifact_id: ArtifactId | None = None
    normalized_artifact_id: ArtifactId | None = None
    applied_snapshot_id: SnapshotId | None = None
    locked_by: str | None = None
    locked_until: datetime | None = None
    retry_count: int = 0
    dirty_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.work_item_id:
            raise DomainInvariantError("work_item_id is required")
        if not self.batch_plan_id:
            raise DomainInvariantError("section work item requires batch_plan_id")
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.section_id:
            raise DomainInvariantError("section work item requires section_id")
        if self.section_index < 0:
            raise DomainInvariantError("section_index must be non-negative")
        if not self.lane_id:
            raise DomainInvariantError("section work item requires lane_id")
        if not self.idempotency_key:
            raise DomainInvariantError("section work item requires idempotency_key")
        if self.retry_count < 0:
            raise DomainInvariantError("retry_count must be non-negative")
        if (
            self.based_on_snapshot_id is None
            and self.based_on_snapshot_sequence_number is not None
        ):
            raise DomainInvariantError(
                "based_on_snapshot_sequence_number requires based_on_snapshot_id"
            )
        if (
            self.based_on_snapshot_sequence_number is not None
            and self.based_on_snapshot_sequence_number < 1
        ):
            raise DomainInvariantError(
                "based_on_snapshot_sequence_number must be positive"
            )
        if (
            self.status is WorkbenchSectionWorkItemStatus.APPLIED
            and not self.applied_snapshot_id
        ):
            raise DomainInvariantError("applied work item requires applied_snapshot_id")


def assign_section_lane_id(
    *,
    position: int,
    total_count: int,
    max_concurrency: int,
) -> str:
    if position < 0:
        raise DomainInvariantError("section position must be non-negative")
    if total_count < 1:
        raise DomainInvariantError("total_count must be positive")
    if max_concurrency < 1:
        raise DomainInvariantError("max_concurrency must be positive")

    lane_count = min(max_concurrency, total_count)
    chunk_size = max(1, ceil(total_count / lane_count))
    lane_number = min(lane_count, position // chunk_size + 1)
    return f"lane-{lane_number}"


def section_work_item_requires_rebase(
    *,
    item: WorkbenchSectionWorkItem,
    latest_snapshot: RegistrySnapshot,
) -> bool:
    if item.status not in {
        WorkbenchSectionWorkItemStatus.FINDINGS_COMPLETED,
        WorkbenchSectionWorkItemStatus.DEDUP_COMPLETED,
        WorkbenchSectionWorkItemStatus.APPLY_PENDING,
        WorkbenchSectionWorkItemStatus.REBASING,
    }:
        return False
    if item.based_on_snapshot_id is None:
        return False
    return item.based_on_snapshot_id != latest_snapshot.snapshot_id


def restore_stale_section_work_item_leases(
    *,
    items: Sequence[WorkbenchSectionWorkItem],
    now: datetime,
) -> tuple[WorkbenchSectionWorkItem, ...]:
    restored: list[WorkbenchSectionWorkItem] = []
    stale_statuses = {
        WorkbenchSectionWorkItemStatus.LEASED,
        WorkbenchSectionWorkItemStatus.FINDINGS_RUNNING,
        WorkbenchSectionWorkItemStatus.REBASING,
    }

    for item in items:
        if (
            item.status in stale_statuses
            and item.locked_until is not None
            and item.locked_until <= now
        ):
            restored.append(
                replace(
                    item,
                    status=WorkbenchSectionWorkItemStatus.PENDING,
                    locked_by=None,
                    locked_until=None,
                    updated_at=now,
                )
            )
        else:
            restored.append(item)

    return tuple(restored)


def runnable_section_work_items(
    items: Sequence[WorkbenchSectionWorkItem],
) -> tuple[WorkbenchSectionWorkItem, ...]:
    return tuple(
        item for item in items if item.status is WorkbenchSectionWorkItemStatus.PENDING
    )


def applied_section_ids(
    items: Sequence[WorkbenchSectionWorkItem],
) -> tuple[SectionId, ...]:
    return tuple(
        item.section_id
        for item in items
        if item.status is WorkbenchSectionWorkItemStatus.APPLIED
    )


def queue_has_unresolved_work(
    items: Sequence[WorkbenchSectionWorkItem],
) -> bool:
    unresolved_statuses = {
        WorkbenchSectionWorkItemStatus.PENDING,
        WorkbenchSectionWorkItemStatus.LEASED,
        WorkbenchSectionWorkItemStatus.FINDINGS_RUNNING,
        WorkbenchSectionWorkItemStatus.FINDINGS_COMPLETED,
        WorkbenchSectionWorkItemStatus.DEDUP_COMPLETED,
        WorkbenchSectionWorkItemStatus.APPLY_PENDING,
        WorkbenchSectionWorkItemStatus.REBASING,
        WorkbenchSectionWorkItemStatus.NEEDS_REVISIT,
    }
    return any(item.status in unresolved_statuses for item in items)
