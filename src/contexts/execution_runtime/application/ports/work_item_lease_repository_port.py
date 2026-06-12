from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(frozen=True, slots=True)
class DueWorkItemRecord:
    work_item: WorkItem
    schedule_payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.work_item, WorkItem):
            raise TypeError("work_item must be WorkItem")
        if self.work_item.status not in {
            WorkItemStatus.READY,
            WorkItemStatus.DEFERRED,
            WorkItemStatus.RETRYABLE_FAILED,
        }:
            raise ValueError("work_item must be due and not leased")
        if not isinstance(self.schedule_payload, Mapping):
            raise TypeError("schedule_payload must be Mapping")


@dataclass(frozen=True, slots=True)
class LeasedWorkItemRecord:
    work_item: WorkItem
    schedule_payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.work_item, WorkItem):
            raise TypeError("work_item must be WorkItem")
        if self.work_item.status is not WorkItemStatus.LEASED:
            raise ValueError("work_item must be leased")
        if not isinstance(self.schedule_payload, Mapping):
            raise TypeError("schedule_payload must be Mapping")


class WorkItemLeaseRepositoryPort(Protocol):
    async def peek_due_work_items(
        self,
        *,
        work_kind: WorkKind,
        requested_items: int,
        now: datetime,
    ) -> tuple[DueWorkItemRecord, ...]: ...

    async def lease_due_work_item(
        self,
        *,
        work_kind: WorkKind,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None: ...
