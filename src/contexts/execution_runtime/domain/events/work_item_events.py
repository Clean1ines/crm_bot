from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


@dataclass(frozen=True, slots=True)
class WorkItemDomainEvent:
    work_item_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.work_item_id or not self.work_item_id.strip():
            raise ValueError("work_item_id must be non-empty")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class WorkItemLeased(WorkItemDomainEvent):
    worker_ref: str


@dataclass(frozen=True, slots=True)
class WorkItemCompleted(WorkItemDomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class WorkItemDeferred(WorkItemDomainEvent):
    wait_until: datetime
    error_kind: str | None = None


@dataclass(frozen=True, slots=True)
class WorkItemFailed(WorkItemDomainEvent):
    status: WorkItemStatus
    error_kind: str


@dataclass(frozen=True, slots=True)
class WorkItemCancelled(WorkItemDomainEvent):
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorkItemLeaseExpired(WorkItemDomainEvent):
    previous_worker_ref: str | None = None
