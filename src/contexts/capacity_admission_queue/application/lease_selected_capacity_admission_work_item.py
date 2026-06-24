from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionAdmitterPort,
    CapacityAdmissionProjectionLease,
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionSelectableWorkItem,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


class TargetedExecutionWorkItemLeasePort(Protocol):
    async def lease_due_work_item_by_id(
        self,
        *,
        work_kind: WorkKind,
        work_item_id: str,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None: ...


@dataclass(frozen=True, slots=True)
class LeaseSelectedCapacityAdmissionWorkItemCommand:
    selected_work_item: CapacityAdmissionSelectableWorkItem
    worker: WorkerRef
    lease_token: LeaseToken
    lease_expires_at: datetime
    now: datetime

    def __post_init__(self) -> None:
        _require_timezone_aware(self.lease_expires_at, "lease_expires_at")
        _require_timezone_aware(self.now, "now")
        if self.lease_expires_at <= self.now:
            raise ValueError("lease_expires_at must be after now")


@dataclass(frozen=True, slots=True)
class LeaseSelectedCapacityAdmissionWorkItemResult:
    execution_lease: LeasedWorkItemRecord | None
    projection_lease: CapacityAdmissionProjectionLeaseResult | None
    skipped_reason: str | None = None

    @property
    def leased(self) -> bool:
        return self.execution_lease is not None and self.projection_lease is not None


@dataclass(frozen=True, slots=True)
class LeaseSelectedCapacityAdmissionWorkItem:
    execution_lease_repository: TargetedExecutionWorkItemLeasePort
    projection_admitter: CapacityAdmissionProjectionAdmitterPort

    async def execute(
        self,
        command: LeaseSelectedCapacityAdmissionWorkItemCommand,
    ) -> LeaseSelectedCapacityAdmissionWorkItemResult:
        selected = command.selected_work_item
        execution_lease = (
            await self.execution_lease_repository.lease_due_work_item_by_id(
                work_kind=WorkKind(selected.lane_key.work_kind),
                work_item_id=selected.work_item_id,
                worker=command.worker,
                lease_token=command.lease_token,
                lease_expires_at=command.lease_expires_at,
                now=command.now,
            )
        )
        if execution_lease is None:
            return LeaseSelectedCapacityAdmissionWorkItemResult(
                execution_lease=None,
                projection_lease=None,
                skipped_reason="execution_work_item_not_leased",
            )

        projection_lease = await self.projection_admitter.admit_projection_work_item(
            CapacityAdmissionProjectionLease(
                work_item_id=selected.work_item_id,
                lane_key=selected.lane_key,
                leased_at=command.now,
            )
        )
        if projection_lease is None:
            return LeaseSelectedCapacityAdmissionWorkItemResult(
                execution_lease=execution_lease,
                projection_lease=None,
                skipped_reason="capacity_projection_not_admitted",
            )

        return LeaseSelectedCapacityAdmissionWorkItemResult(
            execution_lease=execution_lease,
            projection_lease=projection_lease,
        )


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
