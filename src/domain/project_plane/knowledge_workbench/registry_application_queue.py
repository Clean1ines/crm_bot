from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from .registry import RegistrySnapshot
from .shared import (
    DocumentId,
    DomainInvariantError,
    ClaimObservationId,
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


class RegistryApplicationQueueItemStatus(StrEnum):
    READY = "ready"
    LEASED = "leased"
    WAITING_FOR_FRESH_REGISTRY = "waiting_for_fresh_registry"
    APPLIED = "applied"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class RegistryApplicationFreshnessDecision(StrEnum):
    APPLY_NOW = "apply_now"
    REBASE_REQUIRED = "rebase_required"
    WAIT_FOR_SNAPSHOT = "wait_for_snapshot"
    SKIP_TERMINAL = "skip_terminal"


@dataclass(frozen=True, slots=True)
class RegistryApplicationQueueItem:
    queue_item_id: str
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    section_id: SectionId
    source_node_run_id: NodeRunId
    observed_registry_snapshot_id: SnapshotId
    observed_registry_snapshot_sequence: int
    claim_input_refs: tuple[ClaimObservationId, ...]
    status: RegistryApplicationQueueItemStatus
    claimed_by_worker_id: str | None = None
    lease_expires_at: datetime | None = None
    applied_registry_snapshot_id: SnapshotId | None = None
    stale_at_registry_snapshot_id: SnapshotId | None = None
    attempt_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.queue_item_id:
            raise DomainInvariantError("registry application queue_item_id is required")
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        require_node_run_id(self.source_node_run_id)
        if not self.section_id:
            raise DomainInvariantError(
                "registry application queue item requires section_id"
            )
        if not self.observed_registry_snapshot_id:
            raise DomainInvariantError(
                "registry application queue item requires observed registry snapshot"
            )
        if self.observed_registry_snapshot_sequence < 1:
            raise DomainInvariantError(
                "observed registry snapshot sequence must be positive"
            )
        if not self.claim_input_refs:
            raise DomainInvariantError(
                "registry application queue item requires claim_input_refs"
            )
        if self.attempt_count < 0:
            raise DomainInvariantError("registry application attempt_count is negative")

        if self.status is RegistryApplicationQueueItemStatus.LEASED:
            if not self.claimed_by_worker_id:
                raise DomainInvariantError("leased queue item requires worker id")
            if self.lease_expires_at is None:
                raise DomainInvariantError("leased queue item requires lease expiry")

        if (
            self.status is RegistryApplicationQueueItemStatus.APPLIED
            and not self.applied_registry_snapshot_id
        ):
            raise DomainInvariantError(
                "applied queue item requires applied snapshot id"
            )

        if (
            self.status is RegistryApplicationQueueItemStatus.WAITING_FOR_FRESH_REGISTRY
            and not self.stale_at_registry_snapshot_id
        ):
            raise DomainInvariantError(
                "stale queue item requires stale_at_registry_snapshot_id"
            )


@dataclass(frozen=True, slots=True)
class RegistryApplicationFreshnessCheck:
    decision: RegistryApplicationFreshnessDecision
    queue_item_id: str
    observed_registry_snapshot_id: SnapshotId
    observed_registry_snapshot_sequence: int
    latest_registry_snapshot_id: SnapshotId
    latest_registry_snapshot_sequence: int
    reason: str

    @property
    def may_apply(self) -> bool:
        return self.decision is RegistryApplicationFreshnessDecision.APPLY_NOW


def is_terminal_registry_application_status(
    status: RegistryApplicationQueueItemStatus,
) -> bool:
    return status in {
        RegistryApplicationQueueItemStatus.APPLIED,
        RegistryApplicationQueueItemStatus.SUPERSEDED,
        RegistryApplicationQueueItemStatus.FAILED,
    }


def decide_registry_application_freshness(
    *,
    queue_item: RegistryApplicationQueueItem,
    latest_registry_snapshot: RegistrySnapshot,
) -> RegistryApplicationFreshnessCheck:
    _ensure_same_processing_context(queue_item, latest_registry_snapshot)

    if is_terminal_registry_application_status(queue_item.status):
        return _freshness_check(
            queue_item=queue_item,
            latest_registry_snapshot=latest_registry_snapshot,
            decision=RegistryApplicationFreshnessDecision.SKIP_TERMINAL,
            reason="queue item is already terminal",
        )

    if (
        queue_item.observed_registry_snapshot_id == latest_registry_snapshot.snapshot_id
        and queue_item.observed_registry_snapshot_sequence
        == latest_registry_snapshot.sequence_number
    ):
        return _freshness_check(
            queue_item=queue_item,
            latest_registry_snapshot=latest_registry_snapshot,
            decision=RegistryApplicationFreshnessDecision.APPLY_NOW,
            reason="queue item observed the latest registry snapshot",
        )

    if (
        queue_item.observed_registry_snapshot_sequence
        > latest_registry_snapshot.sequence_number
    ):
        return _freshness_check(
            queue_item=queue_item,
            latest_registry_snapshot=latest_registry_snapshot,
            decision=RegistryApplicationFreshnessDecision.WAIT_FOR_SNAPSHOT,
            reason="queue item references a future registry snapshot",
        )

    return _freshness_check(
        queue_item=queue_item,
        latest_registry_snapshot=latest_registry_snapshot,
        decision=RegistryApplicationFreshnessDecision.REBASE_REQUIRED,
        reason="queue item was produced against a stale registry snapshot",
    )


def ensure_registry_application_can_mutate(
    *,
    queue_item: RegistryApplicationQueueItem,
    latest_registry_snapshot: RegistrySnapshot,
) -> None:
    freshness = decide_registry_application_freshness(
        queue_item=queue_item,
        latest_registry_snapshot=latest_registry_snapshot,
    )
    if freshness.may_apply:
        return
    raise DomainInvariantError(
        "registry application queue item requires rebase before mutation: "
        f"{freshness.decision.value}"
    )


def mark_registry_application_item_for_rebase(
    *,
    queue_item: RegistryApplicationQueueItem,
    latest_registry_snapshot: RegistrySnapshot,
    updated_at: datetime | None = None,
) -> RegistryApplicationQueueItem:
    _ensure_same_processing_context(queue_item, latest_registry_snapshot)
    return replace(
        queue_item,
        status=RegistryApplicationQueueItemStatus.WAITING_FOR_FRESH_REGISTRY,
        stale_at_registry_snapshot_id=latest_registry_snapshot.snapshot_id,
        updated_at=updated_at or latest_registry_snapshot.created_at,
    )


def mark_registry_application_item_applied(
    *,
    queue_item: RegistryApplicationQueueItem,
    applied_registry_snapshot: RegistrySnapshot,
    observed_registry_snapshot: RegistrySnapshot | None = None,
    updated_at: datetime | None = None,
) -> RegistryApplicationQueueItem:
    freshness_snapshot = observed_registry_snapshot or applied_registry_snapshot
    ensure_registry_application_can_mutate(
        queue_item=queue_item,
        latest_registry_snapshot=freshness_snapshot,
    )
    _ensure_same_processing_context(queue_item, applied_registry_snapshot)
    if applied_registry_snapshot.sequence_number < freshness_snapshot.sequence_number:
        raise DomainInvariantError(
            "applied registry snapshot cannot be older than observed snapshot"
        )

    return replace(
        queue_item,
        status=RegistryApplicationQueueItemStatus.APPLIED,
        applied_registry_snapshot_id=applied_registry_snapshot.snapshot_id,
        updated_at=updated_at or applied_registry_snapshot.created_at,
    )


def _freshness_check(
    *,
    queue_item: RegistryApplicationQueueItem,
    latest_registry_snapshot: RegistrySnapshot,
    decision: RegistryApplicationFreshnessDecision,
    reason: str,
) -> RegistryApplicationFreshnessCheck:
    return RegistryApplicationFreshnessCheck(
        decision=decision,
        queue_item_id=queue_item.queue_item_id,
        observed_registry_snapshot_id=queue_item.observed_registry_snapshot_id,
        observed_registry_snapshot_sequence=(
            queue_item.observed_registry_snapshot_sequence
        ),
        latest_registry_snapshot_id=latest_registry_snapshot.snapshot_id,
        latest_registry_snapshot_sequence=latest_registry_snapshot.sequence_number,
        reason=reason,
    )


def _ensure_same_processing_context(
    queue_item: RegistryApplicationQueueItem,
    latest_registry_snapshot: RegistrySnapshot,
) -> None:
    if queue_item.processing_run_id != latest_registry_snapshot.processing_run_id:
        raise DomainInvariantError("registry application processing_run mismatch")
    if queue_item.project_id != latest_registry_snapshot.project_id:
        raise DomainInvariantError("registry application project mismatch")
    if queue_item.document_id != latest_registry_snapshot.document_id:
        raise DomainInvariantError("registry application document mismatch")
