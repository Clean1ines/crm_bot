from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from math import ceil

from .documents import DocumentSection
from .registry import RegistrySnapshot
from .shared import (
    DocumentId,
    DomainInvariantError,
    NodeRunId,
    ProcessingRunId,
    ProjectId,
    SectionId,
    SnapshotId,
    require_document_id,
    require_node_run_id,
    require_processing_run_id,
    require_project_id,
)


class SectionBatchQueueItemStatus(StrEnum):
    READY = "ready"
    LEASED = "leased"
    CLAIM_OBSERVATIONS_PERSISTED = "claim_observations_persisted"
    REGISTRY_APPLICATION_QUEUED = "registry_application_queued"
    REGISTRY_APPLICATION_APPLIED = "registry_application_applied"
    WAITING_FOR_FRESH_REGISTRY = "waiting_for_fresh_registry"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SectionBatchQueueItem:
    queue_item_id: str
    batch_plan_id: str
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    section_id: SectionId
    section_key: str
    section_index: int
    lane_id: str
    lane_index: int
    observed_registry_snapshot_id: SnapshotId
    observed_registry_snapshot_sequence: int
    status: SectionBatchQueueItemStatus
    claimed_by_worker_id: str | None = None
    lease_expires_at: datetime | None = None
    claim_observations_node_run_id: NodeRunId | None = None
    registry_application_queue_item_id: str | None = None
    error_kind: str | None = None
    attempt_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.queue_item_id:
            raise DomainInvariantError("section batch queue_item_id is required")
        if not self.batch_plan_id:
            raise DomainInvariantError("section batch_plan_id is required")
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)

        if not self.section_id:
            raise DomainInvariantError("section batch queue item requires section_id")
        if not self.section_key:
            raise DomainInvariantError("section batch queue item requires section_key")
        if self.section_index < 0:
            raise DomainInvariantError("section_index must be non-negative")
        if not self.lane_id:
            raise DomainInvariantError("section batch queue item requires lane_id")
        if self.lane_index < 0:
            raise DomainInvariantError("lane_index must be non-negative")
        if not self.observed_registry_snapshot_id:
            raise DomainInvariantError(
                "section batch queue item requires observed registry snapshot"
            )
        if self.observed_registry_snapshot_sequence < 1:
            raise DomainInvariantError(
                "observed registry snapshot sequence must be positive"
            )
        if self.attempt_count < 0:
            raise DomainInvariantError("section batch attempt_count is negative")

        if self.status is SectionBatchQueueItemStatus.LEASED:
            if not self.claimed_by_worker_id:
                raise DomainInvariantError("leased section item requires worker id")
            if self.lease_expires_at is None:
                raise DomainInvariantError("leased section item requires lease expiry")

        if (
            self.status
            in {
                SectionBatchQueueItemStatus.CLAIM_OBSERVATIONS_PERSISTED,
                SectionBatchQueueItemStatus.REGISTRY_APPLICATION_QUEUED,
                SectionBatchQueueItemStatus.REGISTRY_APPLICATION_APPLIED,
            }
            and not self.claim_observations_node_run_id
        ):
            raise DomainInvariantError(
                f"{self.status.value} section item requires claim observations node run"
            )

        if (
            self.status
            in {
                SectionBatchQueueItemStatus.REGISTRY_APPLICATION_QUEUED,
                SectionBatchQueueItemStatus.REGISTRY_APPLICATION_APPLIED,
            }
            and not self.registry_application_queue_item_id
        ):
            raise DomainInvariantError(
                f"{self.status.value} section item requires registry application queue item"
            )

        if self.status is SectionBatchQueueItemStatus.FAILED and not self.error_kind:
            raise DomainInvariantError("failed section item requires error_kind")


@dataclass(frozen=True, slots=True)
class ParallelSectionLane:
    lane_id: str
    lane_index: int
    section_ids: tuple[SectionId, ...]

    def __post_init__(self) -> None:
        if not self.lane_id:
            raise DomainInvariantError("parallel section lane_id is required")
        if self.lane_index < 0:
            raise DomainInvariantError("parallel section lane_index is negative")
        if not self.section_ids:
            raise DomainInvariantError("parallel section lane must own section ids")


@dataclass(frozen=True, slots=True)
class ParallelSectionBatchPlan:
    batch_plan_id: str
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    observed_registry_snapshot_id: SnapshotId
    observed_registry_snapshot_sequence: int
    max_lanes: int
    lanes: tuple[ParallelSectionLane, ...]
    queue_items: tuple[SectionBatchQueueItem, ...]

    def __post_init__(self) -> None:
        if not self.batch_plan_id:
            raise DomainInvariantError("parallel section batch_plan_id is required")
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.observed_registry_snapshot_id:
            raise DomainInvariantError(
                "parallel section batch requires observed registry snapshot"
            )
        if self.observed_registry_snapshot_sequence < 1:
            raise DomainInvariantError(
                "parallel section batch observed sequence must be positive"
            )
        if self.max_lanes < 1:
            raise DomainInvariantError(
                "parallel section batch max_lanes must be positive"
            )
        if not self.lanes:
            raise DomainInvariantError("parallel section batch requires lanes")
        if not self.queue_items:
            raise DomainInvariantError("parallel section batch requires queue items")

        lane_ids = {lane.lane_id for lane in self.lanes}
        item_lane_ids = {item.lane_id for item in self.queue_items}
        if item_lane_ids - lane_ids:
            raise DomainInvariantError("section queue item references unknown lane")

        for item in self.queue_items:
            if item.batch_plan_id != self.batch_plan_id:
                raise DomainInvariantError("section queue item batch_plan_id mismatch")
            if item.processing_run_id != self.processing_run_id:
                raise DomainInvariantError("section queue item processing_run mismatch")
            if item.project_id != self.project_id:
                raise DomainInvariantError("section queue item project mismatch")
            if item.document_id != self.document_id:
                raise DomainInvariantError("section queue item document mismatch")
            if item.observed_registry_snapshot_id != self.observed_registry_snapshot_id:
                raise DomainInvariantError("section queue item snapshot id mismatch")
            if (
                item.observed_registry_snapshot_sequence
                != self.observed_registry_snapshot_sequence
            ):
                raise DomainInvariantError(
                    "section queue item snapshot sequence mismatch"
                )


def plan_parallel_section_batch(
    *,
    batch_plan_id: str,
    sections: tuple[DocumentSection, ...],
    latest_registry_snapshot: RegistrySnapshot,
    max_lanes: int,
    queue_item_id_prefix: str = "section-batch-item",
) -> ParallelSectionBatchPlan:
    if max_lanes < 1:
        raise DomainInvariantError("parallel section batch max_lanes must be positive")
    if not sections:
        raise DomainInvariantError("parallel section batch requires sections")

    ordered_sections = tuple(
        sorted(sections, key=lambda section: section.section_index)
    )
    lane_count = min(max_lanes, len(ordered_sections))
    chunk_size = ceil(len(ordered_sections) / lane_count)

    lanes: list[ParallelSectionLane] = []
    queue_items: list[SectionBatchQueueItem] = []

    for lane_index in range(lane_count):
        lane_sections = ordered_sections[
            lane_index * chunk_size : (lane_index + 1) * chunk_size
        ]
        if not lane_sections:
            continue

        lane_id = f"section-lane-{lane_index + 1}"
        lanes.append(
            ParallelSectionLane(
                lane_id=lane_id,
                lane_index=lane_index,
                section_ids=tuple(section.section_id for section in lane_sections),
            )
        )

        for section in lane_sections:
            _ensure_section_matches_snapshot(section, latest_registry_snapshot)
            queue_items.append(
                SectionBatchQueueItem(
                    queue_item_id=f"{queue_item_id_prefix}-{section.section_index}",
                    batch_plan_id=batch_plan_id,
                    processing_run_id=latest_registry_snapshot.processing_run_id,
                    project_id=section.project_id,
                    document_id=section.document_id,
                    section_id=section.section_id,
                    section_key=section.section_key,
                    section_index=section.section_index,
                    lane_id=lane_id,
                    lane_index=lane_index,
                    observed_registry_snapshot_id=latest_registry_snapshot.snapshot_id,
                    observed_registry_snapshot_sequence=(
                        latest_registry_snapshot.sequence_number
                    ),
                    status=SectionBatchQueueItemStatus.READY,
                )
            )

    return ParallelSectionBatchPlan(
        batch_plan_id=batch_plan_id,
        processing_run_id=latest_registry_snapshot.processing_run_id,
        project_id=latest_registry_snapshot.project_id,
        document_id=latest_registry_snapshot.document_id,
        observed_registry_snapshot_id=latest_registry_snapshot.snapshot_id,
        observed_registry_snapshot_sequence=latest_registry_snapshot.sequence_number,
        max_lanes=max_lanes,
        lanes=tuple(lanes),
        queue_items=tuple(queue_items),
    )


def mark_section_batch_item_leased(
    *,
    queue_item: SectionBatchQueueItem,
    worker_id: str,
    lease_expires_at: datetime,
    updated_at: datetime | None = None,
) -> SectionBatchQueueItem:
    if not worker_id:
        raise DomainInvariantError("leased section item requires worker id")
    return replace(
        queue_item,
        status=SectionBatchQueueItemStatus.LEASED,
        claimed_by_worker_id=worker_id,
        lease_expires_at=lease_expires_at,
        attempt_count=queue_item.attempt_count + 1,
        updated_at=updated_at,
    )


def mark_section_batch_item_claim_observations_persisted(
    *,
    queue_item: SectionBatchQueueItem,
    claim_observations_node_run_id: NodeRunId,
    updated_at: datetime | None = None,
) -> SectionBatchQueueItem:
    require_node_run_id(claim_observations_node_run_id)
    return replace(
        queue_item,
        status=SectionBatchQueueItemStatus.CLAIM_OBSERVATIONS_PERSISTED,
        claim_observations_node_run_id=claim_observations_node_run_id,
        claimed_by_worker_id=None,
        lease_expires_at=None,
        updated_at=updated_at,
    )


def mark_section_batch_item_registry_application_queued(
    *,
    queue_item: SectionBatchQueueItem,
    registry_application_queue_item_id: str,
    updated_at: datetime | None = None,
) -> SectionBatchQueueItem:
    if not queue_item.claim_observations_node_run_id:
        raise DomainInvariantError(
            "registry application cannot be queued before claim observations"
        )
    if not registry_application_queue_item_id:
        raise DomainInvariantError("registry application queue item id is required")
    return replace(
        queue_item,
        status=SectionBatchQueueItemStatus.REGISTRY_APPLICATION_QUEUED,
        registry_application_queue_item_id=registry_application_queue_item_id,
        claimed_by_worker_id=None,
        lease_expires_at=None,
        updated_at=updated_at,
    )


def mark_section_batch_item_registry_application_applied(
    *,
    queue_item: SectionBatchQueueItem,
    updated_at: datetime | None = None,
) -> SectionBatchQueueItem:
    if not queue_item.registry_application_queue_item_id:
        raise DomainInvariantError(
            "section item cannot be marked applied without registry queue item"
        )
    return replace(
        queue_item,
        status=SectionBatchQueueItemStatus.REGISTRY_APPLICATION_APPLIED,
        claimed_by_worker_id=None,
        lease_expires_at=None,
        updated_at=updated_at,
    )


def _ensure_section_matches_snapshot(
    section: DocumentSection,
    latest_registry_snapshot: RegistrySnapshot,
) -> None:
    if section.project_id != latest_registry_snapshot.project_id:
        raise DomainInvariantError("section batch project mismatch")
    if section.document_id != latest_registry_snapshot.document_id:
        raise DomainInvariantError("section batch document mismatch")
