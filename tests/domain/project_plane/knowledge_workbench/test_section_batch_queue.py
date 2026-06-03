from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
    DomainInvariantError,
    RegistrySnapshot,
    SectionBatchQueueItemStatus,
    mark_section_batch_item_claim_observations_persisted,
    mark_section_batch_item_leased,
    mark_section_batch_item_registry_application_applied,
    mark_section_batch_item_registry_application_queued,
    plan_parallel_section_batch,
)


def _section_status() -> DocumentSectionStatus:
    for status in DocumentSectionStatus:
        if status.value not in {"deleted", "failed"}:
            return status
    raise AssertionError("DocumentSectionStatus has no usable non-terminal status")


def _section(index: int) -> DocumentSection:
    return DocumentSection(
        section_id=f"section-{index + 1}",
        document_id="document-1",
        project_id="project-1",
        section_index=index,
        section_key=f"section_{index + 1}",
        heading_path=(f"Section {index + 1}",),
        title=f"Section {index + 1}",
        raw_text=f"Raw section {index + 1}",
        normalized_text=f"Normalized section {index + 1}",
        source_refs=(f"document-1#section-{index + 1}",),
        source_chunk_indexes=(index,),
        parent_section_id=None,
        status=_section_status(),
        metadata={},
    )


def _snapshot(
    *,
    snapshot_id: str = "snapshot-1",
    sequence_number: int = 1,
) -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id=snapshot_id,
        registry_id="registry-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        after_node_run_id="node-run-registry-application",
        sequence_number=sequence_number,
        entries_payload={"entries": []},
        relations_payload={"relations": []},
        entry_count=0,
        relation_count=0,
        claim_observation_count=0,
        update_count=0,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def test_parallel_section_batch_plan_splits_sections_into_contiguous_lanes() -> None:
    sections = tuple(_section(index) for index in range(6))

    plan = plan_parallel_section_batch(
        batch_plan_id="batch-plan-1",
        sections=sections,
        latest_registry_snapshot=_snapshot(),
        max_lanes=3,
    )

    assert plan.max_lanes == 3
    assert len(plan.lanes) == 3
    assert tuple(lane.section_ids for lane in plan.lanes) == (
        ("section-1", "section-2"),
        ("section-3", "section-4"),
        ("section-5", "section-6"),
    )

    assert tuple(item.lane_id for item in plan.queue_items) == (
        "section-lane-1",
        "section-lane-1",
        "section-lane-2",
        "section-lane-2",
        "section-lane-3",
        "section-lane-3",
    )


def test_parallel_section_batch_items_capture_observed_registry_snapshot() -> None:
    sections = tuple(_section(index) for index in range(3))
    snapshot = _snapshot(snapshot_id="snapshot-7", sequence_number=7)

    plan = plan_parallel_section_batch(
        batch_plan_id="batch-plan-1",
        sections=sections,
        latest_registry_snapshot=snapshot,
        max_lanes=3,
    )

    assert all(
        item.observed_registry_snapshot_id == "snapshot-7" for item in plan.queue_items
    )
    assert all(
        item.observed_registry_snapshot_sequence == 7 for item in plan.queue_items
    )
    assert all(
        item.status is SectionBatchQueueItemStatus.READY for item in plan.queue_items
    )


def test_parallel_section_batch_rejects_invalid_lane_count() -> None:
    with pytest.raises(DomainInvariantError, match="max_lanes"):
        plan_parallel_section_batch(
            batch_plan_id="batch-plan-1",
            sections=(_section(0),),
            latest_registry_snapshot=_snapshot(),
            max_lanes=0,
        )


def test_parallel_section_batch_rejects_empty_sections() -> None:
    with pytest.raises(DomainInvariantError, match="requires sections"):
        plan_parallel_section_batch(
            batch_plan_id="batch-plan-1",
            sections=(),
            latest_registry_snapshot=_snapshot(),
            max_lanes=3,
        )


def test_section_batch_item_lifecycle_records_worker_and_registry_queue_link() -> None:
    plan = plan_parallel_section_batch(
        batch_plan_id="batch-plan-1",
        sections=(_section(0),),
        latest_registry_snapshot=_snapshot(),
        max_lanes=3,
    )
    item = plan.queue_items[0]
    lease_expiry = datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(minutes=5)

    leased = mark_section_batch_item_leased(
        queue_item=item,
        worker_id="section-worker-1",
        lease_expires_at=lease_expiry,
    )
    assert leased.status is SectionBatchQueueItemStatus.LEASED
    assert leased.claimed_by_worker_id == "section-worker-1"
    assert leased.attempt_count == 1

    claim_observations_persisted = mark_section_batch_item_claim_observations_persisted(
        queue_item=leased,
        claim_observations_node_run_id="node-run-claim-observations-1",
    )
    assert claim_observations_persisted.status is SectionBatchQueueItemStatus.CLAIM_OBSERVATIONS_PERSISTED
    assert claim_observations_persisted.claim_observations_node_run_id == (
        "node-run-claim-observations-1"
    )
    assert claim_observations_persisted.claimed_by_worker_id is None

    registry_queued = mark_section_batch_item_registry_application_queued(
        queue_item=claim_observations_persisted,
        registry_application_queue_item_id="registry-application-queue-item-1",
    )
    assert (
        registry_queued.status
        is SectionBatchQueueItemStatus.REGISTRY_APPLICATION_QUEUED
    )
    assert registry_queued.registry_application_queue_item_id == (
        "registry-application-queue-item-1"
    )

    applied = mark_section_batch_item_registry_application_applied(
        queue_item=registry_queued,
    )
    assert applied.status is SectionBatchQueueItemStatus.REGISTRY_APPLICATION_APPLIED


def test_registry_application_cannot_be_queued_before_findings_are_persisted() -> None:
    plan = plan_parallel_section_batch(
        batch_plan_id="batch-plan-1",
        sections=(_section(0),),
        latest_registry_snapshot=_snapshot(),
        max_lanes=3,
    )

    with pytest.raises(DomainInvariantError, match="before claim observations"):
        mark_section_batch_item_registry_application_queued(
            queue_item=plan.queue_items[0],
            registry_application_queue_item_id="registry-application-queue-item-1",
        )


def test_section_batch_rejects_section_from_other_document() -> None:
    bad_section = DocumentSection(
        section_id="section-bad",
        document_id="other-document",
        project_id="project-1",
        section_index=0,
        section_key="bad",
        heading_path=("Bad",),
        title="Bad",
        raw_text="Bad",
        normalized_text="Bad",
        source_refs=("other#section",),
        source_chunk_indexes=(0,),
        parent_section_id=None,
        status=_section_status(),
        metadata={},
    )

    with pytest.raises(DomainInvariantError, match="document mismatch"):
        plan_parallel_section_batch(
            batch_plan_id="batch-plan-1",
            sections=(bad_section,),
            latest_registry_snapshot=_snapshot(),
            max_lanes=3,
        )
