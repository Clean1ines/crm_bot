from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(frozen=True, slots=True)
class WorkItem:
    """Canonical generic unit of executable work.

    WorkItem is intentionally context-agnostic. It owns execution lifecycle only:
    readiness, leasing, retry/failure/cancellation and terminal completion.
    """

    work_item_id: str
    work_kind: WorkKind
    status: WorkItemStatus = WorkItemStatus.READY
    attempt_count: int = 0
    leased_by: WorkerRef | None = None
    lease_token: LeaseToken | None = None
    lease_expires_at: datetime | None = None
    last_error_kind: str | None = None
    retry_plan: WorkItemRetryPlan | None = None

    def __post_init__(self) -> None:
        if not self.work_item_id or not self.work_item_id.strip():
            raise ValueError("WorkItem.work_item_id must be non-empty")
        if self.attempt_count < 0:
            raise ValueError("WorkItem.attempt_count must be >= 0")

        if self.status is WorkItemStatus.LEASED:
            if self.leased_by is None:
                raise ValueError("LEASED WorkItem must have leased_by")
            if self.lease_token is None:
                raise ValueError("LEASED WorkItem must have lease_token")
            if self.lease_expires_at is None:
                raise ValueError("LEASED WorkItem must have lease_expires_at")
            if (
                self.lease_expires_at.tzinfo is None
                or self.lease_expires_at.utcoffset() is None
            ):
                raise ValueError("lease_expires_at must be timezone-aware")

        if self.status is not WorkItemStatus.LEASED:
            if (
                self.leased_by is not None
                or self.lease_token is not None
                or self.lease_expires_at is not None
            ):
                raise ValueError("Only LEASED WorkItem may carry lease fields")

    def has_active_lease(self, now: datetime) -> bool:
        if self.status is not WorkItemStatus.LEASED or self.lease_expires_at is None:
            return False
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return self.lease_expires_at > now

    def is_due(self, now: datetime) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return self.status in {
            WorkItemStatus.READY,
            WorkItemStatus.RETRYABLE_FAILED,
        }
