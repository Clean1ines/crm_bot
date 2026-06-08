from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


class InvalidWorkItemTransition(ValueError):
    """Raised when a WorkItem lifecycle transition violates the state machine."""


class WorkItemStateMachine:
    """Canonical state machine for Execution Runtime work items."""

    @staticmethod
    def lease_ready(
        item: WorkItem,
        *,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> WorkItem:
        if item.status not in {
            WorkItemStatus.READY,
            WorkItemStatus.DEFERRED,
            WorkItemStatus.RETRYABLE_FAILED,
        }:
            raise InvalidWorkItemTransition(
                f"Cannot lease work item from status {item.status}"
            )

        if item.next_attempt_at is not None and item.next_attempt_at.value > now:
            raise InvalidWorkItemTransition(
                "Cannot lease work item before next_attempt_at"
            )

        if lease_expires_at <= now:
            raise InvalidWorkItemTransition("lease_expires_at must be in the future")

        return replace(
            item,
            status=WorkItemStatus.LEASED,
            attempt_count=item.attempt_count + 1,
            leased_by=worker,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            next_attempt_at=None,
            last_error_kind=None,
        )

    @staticmethod
    def complete_leased(item: WorkItem) -> WorkItem:
        WorkItemStateMachine._require_leased(item, "complete")
        return replace(
            item,
            status=WorkItemStatus.COMPLETED,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=None,
            last_error_kind=None,
        )

    @staticmethod
    def defer_leased(
        item: WorkItem,
        *,
        wait_until: WaitUntil,
        error_kind: str | None = None,
    ) -> WorkItem:
        WorkItemStateMachine._require_leased(item, "defer")
        return replace(
            item,
            status=WorkItemStatus.DEFERRED,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=wait_until,
            last_error_kind=error_kind,
        )

    @staticmethod
    def fail_leased_retryable(
        item: WorkItem,
        *,
        error_kind: str,
        next_attempt_at: WaitUntil,
    ) -> WorkItem:
        WorkItemStateMachine._require_leased(item, "mark retryable failed")
        if not error_kind or not error_kind.strip():
            raise ValueError("error_kind must be non-empty")
        return replace(
            item,
            status=WorkItemStatus.RETRYABLE_FAILED,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=next_attempt_at,
            last_error_kind=error_kind,
        )

    @staticmethod
    def fail_leased_terminal(item: WorkItem, *, error_kind: str) -> WorkItem:
        WorkItemStateMachine._require_leased(item, "mark terminal failed")
        if not error_kind or not error_kind.strip():
            raise ValueError("error_kind must be non-empty")
        return replace(
            item,
            status=WorkItemStatus.TERMINAL_FAILED,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=None,
            last_error_kind=error_kind,
        )

    @staticmethod
    def cancel(item: WorkItem, *, error_kind: str | None = "cancelled") -> WorkItem:
        if item.status.is_terminal:
            raise InvalidWorkItemTransition(
                f"Cannot cancel terminal work item from status {item.status}"
            )
        return replace(
            item,
            status=WorkItemStatus.CANCELLED,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=None,
            last_error_kind=error_kind,
        )

    @staticmethod
    def mark_split_superseded_leased(item: WorkItem) -> WorkItem:
        WorkItemStateMachine._require_leased(item, "mark split superseded")
        return replace(
            item,
            status=WorkItemStatus.SPLIT_SUPERSEDED,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=None,
            last_error_kind=None,
        )

    @staticmethod
    def reclaim_expired_lease(item: WorkItem, *, now: datetime) -> WorkItem:
        if item.status is not WorkItemStatus.LEASED:
            return item
        if item.lease_expires_at is None:
            raise InvalidWorkItemTransition(
                "LEASED work item is missing lease_expires_at"
            )
        if item.lease_expires_at > now:
            return item
        return replace(
            item,
            status=WorkItemStatus.READY,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=None,
            last_error_kind="lease_expired",
        )

    @staticmethod
    def _require_leased(item: WorkItem, action: str) -> None:
        if item.status is not WorkItemStatus.LEASED:
            raise InvalidWorkItemTransition(
                f"Cannot {action} work item from status {item.status}"
            )
