from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench.registry_application_queue import (
    RegistryApplicationFreshnessDecision,
    RegistryApplicationQueueItem,
    RegistryApplicationQueueItemStatus,
    decide_registry_application_freshness,
    ensure_registry_application_can_mutate,
    mark_registry_application_item_applied,
    mark_registry_application_item_for_rebase,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    RegistrySnapshot,
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
        entry_count=1,
        relation_count=0,
        claim_observation_count=1,
        update_count=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _queue_item(
    *,
    observed_snapshot_id: str = "snapshot-1",
    observed_sequence: int = 1,
    status: RegistryApplicationQueueItemStatus = RegistryApplicationQueueItemStatus.READY,
) -> RegistryApplicationQueueItem:
    return RegistryApplicationQueueItem(
        queue_item_id="registry-queue-item-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        source_node_run_id="claim-observations-node-run-1",
        observed_registry_snapshot_id=observed_snapshot_id,
        observed_registry_snapshot_sequence=observed_sequence,
        claim_input_refs=("finding-1",),
        status=status,
    )


def test_queue_item_observing_latest_snapshot_may_apply() -> None:
    item = _queue_item()
    latest_snapshot = _snapshot()

    decision = decide_registry_application_freshness(
        queue_item=item,
        latest_registry_snapshot=latest_snapshot,
    )

    assert decision.decision is RegistryApplicationFreshnessDecision.APPLY_NOW
    assert decision.may_apply is True

    ensure_registry_application_can_mutate(
        queue_item=item,
        latest_registry_snapshot=latest_snapshot,
    )

    applied = mark_registry_application_item_applied(
        queue_item=item,
        applied_registry_snapshot=latest_snapshot,
    )

    assert applied.status is RegistryApplicationQueueItemStatus.APPLIED
    assert applied.applied_registry_snapshot_id == "snapshot-1"


def test_queue_item_from_stale_snapshot_requires_rebase_before_mutation() -> None:
    item = _queue_item(observed_snapshot_id="snapshot-1", observed_sequence=1)
    latest_snapshot = _snapshot(snapshot_id="snapshot-2", sequence_number=2)

    decision = decide_registry_application_freshness(
        queue_item=item,
        latest_registry_snapshot=latest_snapshot,
    )

    assert decision.decision is RegistryApplicationFreshnessDecision.REBASE_REQUIRED
    assert decision.may_apply is False

    with pytest.raises(DomainInvariantError, match="requires rebase"):
        ensure_registry_application_can_mutate(
            queue_item=item,
            latest_registry_snapshot=latest_snapshot,
        )

    stale = mark_registry_application_item_for_rebase(
        queue_item=item,
        latest_registry_snapshot=latest_snapshot,
    )

    assert stale.status is RegistryApplicationQueueItemStatus.WAITING_FOR_FRESH_REGISTRY
    assert stale.stale_at_registry_snapshot_id == "snapshot-2"


def test_queue_item_referencing_future_snapshot_waits_for_snapshot() -> None:
    item = _queue_item(observed_snapshot_id="snapshot-2", observed_sequence=2)
    latest_snapshot = _snapshot(snapshot_id="snapshot-1", sequence_number=1)

    decision = decide_registry_application_freshness(
        queue_item=item,
        latest_registry_snapshot=latest_snapshot,
    )

    assert decision.decision is RegistryApplicationFreshnessDecision.WAIT_FOR_SNAPSHOT
    assert decision.may_apply is False


def test_terminal_queue_item_is_skipped_even_if_snapshot_matches() -> None:
    item = RegistryApplicationQueueItem(
        queue_item_id="registry-queue-item-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        source_node_run_id="claim-observations-node-run-1",
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        claim_input_refs=("finding-1",),
        status=RegistryApplicationQueueItemStatus.APPLIED,
        applied_registry_snapshot_id="snapshot-1",
    )

    decision = decide_registry_application_freshness(
        queue_item=item,
        latest_registry_snapshot=_snapshot(),
    )

    assert decision.decision is RegistryApplicationFreshnessDecision.SKIP_TERMINAL
    assert decision.may_apply is False


def test_queue_item_requires_claim_input_refs() -> None:
    with pytest.raises(DomainInvariantError, match="claim_input_refs"):
        RegistryApplicationQueueItem(
            queue_item_id="registry-queue-item-1",
            processing_run_id="processing-run-1",
            project_id="project-1",
            document_id="document-1",
            section_id="section-1",
            source_node_run_id="claim-observations-node-run-1",
            observed_registry_snapshot_id="snapshot-1",
            observed_registry_snapshot_sequence=1,
            claim_input_refs=(),
            status=RegistryApplicationQueueItemStatus.READY,
        )


def test_leased_queue_item_requires_worker_and_lease_expiry() -> None:
    with pytest.raises(DomainInvariantError, match="worker id"):
        RegistryApplicationQueueItem(
            queue_item_id="registry-queue-item-1",
            processing_run_id="processing-run-1",
            project_id="project-1",
            document_id="document-1",
            section_id="section-1",
            source_node_run_id="claim-observations-node-run-1",
            observed_registry_snapshot_id="snapshot-1",
            observed_registry_snapshot_sequence=1,
            claim_input_refs=("finding-1",),
            status=RegistryApplicationQueueItemStatus.LEASED,
        )


def test_mark_applied_allows_new_after_snapshot_when_item_observed_previous_latest_snapshot() -> (
    None
):
    item = _queue_item(observed_snapshot_id="snapshot-1", observed_sequence=1)
    observed_snapshot = _snapshot(snapshot_id="snapshot-1", sequence_number=1)
    applied_snapshot = _snapshot(snapshot_id="snapshot-2", sequence_number=2)

    applied = mark_registry_application_item_applied(
        queue_item=item,
        observed_registry_snapshot=observed_snapshot,
        applied_registry_snapshot=applied_snapshot,
    )

    assert applied.status is RegistryApplicationQueueItemStatus.APPLIED
    assert applied.applied_registry_snapshot_id == "snapshot-2"
