from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


class ClaimExtractionStageProgressStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_QUOTA = "waiting_for_quota"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_USER_CHOICE = "requires_user_choice"
    CANCELLED = "cancelled"
    PARTIAL_CANCELLED = "partial_cancelled"


class ClaimExtractionStageBlockerKind(StrEnum):
    ACTIVE_LEASE = "active_lease"
    QUOTA_WAIT = "quota_wait"
    WAITING = "waiting"
    TERMINAL_FAILED = "terminal_failed"
    USER_ACTION_REQUIRED = "user_action_required"
    CANCELLED = "cancelled"


class ClaimExtractionStageProgressQueryPort(Protocol):
    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]: ...

    def count_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class ClaimExtractionStageProgressQuery:
    workflow_run_id: str
    stage_run_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.stage_run_id, "stage_run_id")


@dataclass(frozen=True, slots=True)
class ClaimExtractionStageProgress:
    status: ClaimExtractionStageProgressStatus
    ready_count: int
    leased_count: int
    deferred_count: int
    completed_count: int
    retryable_failed_count: int
    terminal_failed_count: int
    cancelled_count: int
    split_superseded_count: int
    artifacts_count: int
    nearest_wait_until: datetime | None
    blocker_kind: ClaimExtractionStageBlockerKind | None
    user_action_required_count: int

    @property
    def total_work_item_count(self) -> int:
        return (
            self.ready_count
            + self.leased_count
            + self.deferred_count
            + self.completed_count
            + self.retryable_failed_count
            + self.terminal_failed_count
            + self.cancelled_count
            + self.split_superseded_count
            + self.user_action_required_count
        )


class ClaimExtractionStageProgressReadModel:
    def __init__(self, *, query_port: ClaimExtractionStageProgressQueryPort) -> None:
        self._query_port = query_port

    def execute(
        self,
        query: ClaimExtractionStageProgressQuery,
    ) -> ClaimExtractionStageProgress:
        work_items = self._query_port.load_work_items(
            workflow_run_id=query.workflow_run_id,
            stage_run_id=query.stage_run_id,
        )
        artifacts_count = self._query_port.count_artifacts(
            workflow_run_id=query.workflow_run_id,
            stage_run_id=query.stage_run_id,
        )
        if artifacts_count < 0:
            raise ValueError("artifacts_count must be >= 0")

        ready_count = _count_status(work_items, WorkItemStatus.READY)
        leased_count = _count_status(work_items, WorkItemStatus.LEASED)
        deferred_count = _count_status(work_items, WorkItemStatus.DEFERRED)
        completed_count = _count_status(work_items, WorkItemStatus.COMPLETED)
        retryable_failed_count = _count_status(
            work_items,
            WorkItemStatus.RETRYABLE_FAILED,
        )
        terminal_failed_count = _count_status(
            work_items,
            WorkItemStatus.TERMINAL_FAILED,
        )
        cancelled_count = _count_status(work_items, WorkItemStatus.CANCELLED)
        split_superseded_count = _count_status(
            work_items,
            WorkItemStatus.SPLIT_SUPERSEDED,
        )
        user_action_required_count = _count_status(
            work_items,
            WorkItemStatus.USER_ACTION_REQUIRED,
        )
        nearest_wait_until = _nearest_wait_until(work_items)
        total_count = len(work_items)

        return ClaimExtractionStageProgress(
            status=_progress_status(
                total_count=total_count,
                ready_count=ready_count,
                leased_count=leased_count,
                deferred_count=deferred_count,
                completed_count=completed_count,
                retryable_failed_count=retryable_failed_count,
                terminal_failed_count=terminal_failed_count,
                cancelled_count=cancelled_count,
                split_superseded_count=split_superseded_count,
                user_action_required_count=user_action_required_count,
            ),
            ready_count=ready_count,
            leased_count=leased_count,
            deferred_count=deferred_count,
            completed_count=completed_count,
            retryable_failed_count=retryable_failed_count,
            terminal_failed_count=terminal_failed_count,
            cancelled_count=cancelled_count,
            split_superseded_count=split_superseded_count,
            artifacts_count=artifacts_count,
            nearest_wait_until=nearest_wait_until,
            blocker_kind=_blocker_kind(
                leased_count=leased_count,
                deferred_count=deferred_count,
                retryable_failed_count=retryable_failed_count,
                terminal_failed_count=terminal_failed_count,
                cancelled_count=cancelled_count,
                user_action_required_count=user_action_required_count,
                nearest_wait_until=nearest_wait_until,
            ),
            user_action_required_count=user_action_required_count,
        )


def _count_status(work_items: tuple[WorkItem, ...], status: WorkItemStatus) -> int:
    return sum(1 for item in work_items if item.status is status)


def _nearest_wait_until(work_items: tuple[WorkItem, ...]) -> datetime | None:
    waits = tuple(
        item.next_attempt_at.value
        for item in work_items
        if item.status
        in {
            WorkItemStatus.DEFERRED,
            WorkItemStatus.RETRYABLE_FAILED,
        }
        and item.next_attempt_at is not None
    )
    if not waits:
        return None
    return min(waits)


def _progress_status(
    *,
    total_count: int,
    ready_count: int,
    leased_count: int,
    deferred_count: int,
    completed_count: int,
    retryable_failed_count: int,
    terminal_failed_count: int,
    cancelled_count: int,
    split_superseded_count: int,
    user_action_required_count: int,
) -> ClaimExtractionStageProgressStatus:
    if total_count == 0:
        return ClaimExtractionStageProgressStatus.PENDING

    if terminal_failed_count > 0:
        return ClaimExtractionStageProgressStatus.FAILED

    if user_action_required_count > 0:
        return ClaimExtractionStageProgressStatus.REQUIRES_USER_CHOICE

    if leased_count > 0:
        return ClaimExtractionStageProgressStatus.IN_PROGRESS

    if cancelled_count == total_count:
        return ClaimExtractionStageProgressStatus.CANCELLED

    if cancelled_count > 0:
        return ClaimExtractionStageProgressStatus.PARTIAL_CANCELLED

    completed_total = completed_count + split_superseded_count
    if completed_total == total_count:
        return ClaimExtractionStageProgressStatus.COMPLETED

    if deferred_count > 0 or retryable_failed_count > 0:
        return ClaimExtractionStageProgressStatus.WAITING_FOR_QUOTA

    if ready_count > 0:
        return ClaimExtractionStageProgressStatus.PENDING

    return ClaimExtractionStageProgressStatus.WAITING


def _blocker_kind(
    *,
    leased_count: int,
    deferred_count: int,
    retryable_failed_count: int,
    terminal_failed_count: int,
    cancelled_count: int,
    user_action_required_count: int,
    nearest_wait_until: datetime | None,
) -> ClaimExtractionStageBlockerKind | None:
    if terminal_failed_count > 0:
        return ClaimExtractionStageBlockerKind.TERMINAL_FAILED
    if user_action_required_count > 0:
        return ClaimExtractionStageBlockerKind.USER_ACTION_REQUIRED
    if leased_count > 0:
        return ClaimExtractionStageBlockerKind.ACTIVE_LEASE
    if deferred_count > 0 or retryable_failed_count > 0:
        if nearest_wait_until is not None:
            return ClaimExtractionStageBlockerKind.QUOTA_WAIT
        return ClaimExtractionStageBlockerKind.WAITING
    if cancelled_count > 0:
        return ClaimExtractionStageBlockerKind.CANCELLED
    return None


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
