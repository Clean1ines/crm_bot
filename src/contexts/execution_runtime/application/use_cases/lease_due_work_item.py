from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(frozen=True, slots=True)
class LeaseDueWorkItemCommand:
    work_kind: WorkKind
    worker: WorkerRef
    lease_token: LeaseToken
    lease_expires_at: datetime
    now: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        if not isinstance(self.worker, WorkerRef):
            raise TypeError("worker must be WorkerRef")
        if not isinstance(self.lease_token, LeaseToken):
            raise TypeError("lease_token must be LeaseToken")
        _require_timezone_aware(self.now, field_name="now")
        _require_timezone_aware(
            self.lease_expires_at,
            field_name="lease_expires_at",
        )
        if self.lease_expires_at <= self.now:
            raise ValueError("lease_expires_at must be > now")


@dataclass(frozen=True, slots=True)
class LeaseDueWorkItemResult:
    leased: LeasedWorkItemRecord | None

    def __post_init__(self) -> None:
        if self.leased is not None and not isinstance(
            self.leased, LeasedWorkItemRecord
        ):
            raise TypeError("leased must be LeasedWorkItemRecord or None")


@dataclass(frozen=True, slots=True)
class LeaseDueWorkItem:
    repository: WorkItemLeaseRepositoryPort

    async def execute(
        self,
        command: LeaseDueWorkItemCommand,
    ) -> LeaseDueWorkItemResult:
        leased = await self.repository.lease_due_work_item(
            work_kind=command.work_kind,
            worker=command.worker,
            lease_token=command.lease_token,
            lease_expires_at=command.lease_expires_at,
            now=command.now,
        )
        return LeaseDueWorkItemResult(leased=leased)


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
