from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.capacity_runtime.domain.capacity_decision import (
    CapacityDecision,
    CapacityNeed,
    CapacityRequest,
    CapacitySnapshot,
    CapacityWorkClass,
)
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.lease_due_work_item import (
    LeaseDueWorkItem,
    LeaseDueWorkItemCommand,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(frozen=True, slots=True)
class LeaseAdmittedWorkItemsCommand:
    work_kind: WorkKind
    work_class: CapacityWorkClass
    capacity_needs: tuple[CapacityNeed, ...]
    capacity_snapshot: CapacitySnapshot
    requested_items: int
    worker: WorkerRef
    lease_token_prefix: str
    lease_expires_at: datetime
    now: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        if not isinstance(self.work_class, CapacityWorkClass):
            raise TypeError("work_class must be CapacityWorkClass")
        if not isinstance(self.capacity_needs, tuple):
            raise TypeError("capacity_needs must be tuple")
        if not self.capacity_needs:
            raise ValueError("capacity_needs must be non-empty")
        for need in self.capacity_needs:
            if not isinstance(need, CapacityNeed):
                raise TypeError("capacity_needs must contain CapacityNeed")
        if not isinstance(self.capacity_snapshot, CapacitySnapshot):
            raise TypeError("capacity_snapshot must be CapacitySnapshot")
        if not isinstance(self.requested_items, int):
            raise TypeError("requested_items must be int")
        if self.requested_items <= 0:
            raise ValueError("requested_items must be > 0")
        if not isinstance(self.worker, WorkerRef):
            raise TypeError("worker must be WorkerRef")
        if not isinstance(self.lease_token_prefix, str):
            raise TypeError("lease_token_prefix must be str")
        if not self.lease_token_prefix.strip():
            raise ValueError("lease_token_prefix must be non-empty")
        _require_timezone_aware(self.now, field_name="now")
        _require_timezone_aware(
            self.lease_expires_at,
            field_name="lease_expires_at",
        )
        if self.lease_expires_at <= self.now:
            raise ValueError("lease_expires_at must be > now")


@dataclass(frozen=True, slots=True)
class LeaseAdmittedWorkItemsResult:
    capacity_decision: CapacityDecision
    leased: tuple[LeasedWorkItemRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.capacity_decision, CapacityDecision):
            raise TypeError("capacity_decision must be CapacityDecision")
        if not isinstance(self.leased, tuple):
            raise TypeError("leased must be tuple")
        for item in self.leased:
            if not isinstance(item, LeasedWorkItemRecord):
                raise TypeError("leased must contain LeasedWorkItemRecord")
        if len(self.leased) > self.capacity_decision.max_admissible_items:
            raise ValueError("leased length must not exceed max_admissible_items")


@dataclass(frozen=True, slots=True)
class LeaseAdmittedWorkItems:
    repository: WorkItemLeaseRepositoryPort
    capacity_policy: CapacityAdmissionPolicy

    async def execute(
        self,
        command: LeaseAdmittedWorkItemsCommand,
    ) -> LeaseAdmittedWorkItemsResult:
        capacity_request = CapacityRequest(
            work_class=command.work_class,
            needs=command.capacity_needs,
            requested_items=command.requested_items,
        )
        decision = self.capacity_policy.decide(
            request=capacity_request,
            snapshot=command.capacity_snapshot,
        )
        if decision.max_admissible_items == 0:
            return LeaseAdmittedWorkItemsResult(
                capacity_decision=decision,
                leased=(),
            )

        leased_records: list[LeasedWorkItemRecord] = []
        lease_due_work_item = LeaseDueWorkItem(repository=self.repository)
        for index in range(decision.max_admissible_items):
            result = await lease_due_work_item.execute(
                LeaseDueWorkItemCommand(
                    work_kind=command.work_kind,
                    worker=command.worker,
                    lease_token=LeaseToken(f"{command.lease_token_prefix}:{index}"),
                    lease_expires_at=command.lease_expires_at,
                    now=command.now,
                ),
            )
            if result.leased is None:
                break
            leased_records.append(result.leased)

        return LeaseAdmittedWorkItemsResult(
            capacity_decision=decision,
            leased=tuple(leased_records),
        )


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
