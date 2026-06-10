from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.capacity_runtime.domain.capacity_decision import CapacityWorkClass
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.lease_admitted_work_items import (
    LeaseAdmittedWorkItems,
    LeaseAdmittedWorkItemsCommand,
    LeaseAdmittedWorkItemsResult,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    LlmCapacityAllocationSlot,
    LlmCapacityProjectionCommand,
    LlmCapacityProjectionResult,
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


@dataclass(frozen=True, slots=True)
class LlmAdmittedLeasedWorkItem:
    leased: LeasedWorkItemRecord
    allocation: LlmCapacityAllocationSlot

    def __post_init__(self) -> None:
        if not isinstance(self.leased, LeasedWorkItemRecord):
            raise TypeError("leased must be LeasedWorkItemRecord")
        if not isinstance(self.allocation, LlmCapacityAllocationSlot):
            raise TypeError("allocation must be LlmCapacityAllocationSlot")

    def to_dispatch_payload(self) -> dict[str, object]:
        return {
            "work_item_id": self.leased.work_item.work_item_id,
            "schedule_payload": dict(self.leased.schedule_payload),
            "llm_allocation": self.allocation.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class LeaseLlmAdmittedWorkItemsCommand:
    work_kind: WorkKind
    profile: LlmTaskCapacityProfile
    accounts: tuple[LlmProviderAccountCapacity, ...]
    requested_items: int
    worker: WorkerRef
    lease_token_prefix: str
    lease_expires_at: datetime
    now: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        if not isinstance(self.profile, LlmTaskCapacityProfile):
            raise TypeError("profile must be LlmTaskCapacityProfile")
        if not isinstance(self.accounts, tuple):
            raise TypeError("accounts must be tuple")
        if not self.accounts:
            raise ValueError("accounts must be non-empty")
        for account in self.accounts:
            if not isinstance(account, LlmProviderAccountCapacity):
                raise TypeError("accounts must contain LlmProviderAccountCapacity")
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
class LeaseLlmAdmittedWorkItemsResult:
    llm_capacity_projection: LlmCapacityProjectionResult
    lease_result: LeaseAdmittedWorkItemsResult
    leased: tuple[LlmAdmittedLeasedWorkItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.llm_capacity_projection, LlmCapacityProjectionResult):
            raise TypeError(
                "llm_capacity_projection must be LlmCapacityProjectionResult",
            )
        if not isinstance(self.lease_result, LeaseAdmittedWorkItemsResult):
            raise TypeError("lease_result must be LeaseAdmittedWorkItemsResult")
        if not isinstance(self.leased, tuple):
            raise TypeError("leased must be tuple")
        for item in self.leased:
            if not isinstance(item, LlmAdmittedLeasedWorkItem):
                raise TypeError("leased must contain LlmAdmittedLeasedWorkItem")
        if len(self.leased) != len(self.lease_result.leased):
            raise ValueError("leased length must equal lease_result leased length")
        if len(self.leased) > len(self.llm_capacity_projection.allocations):
            raise ValueError("leased length must not exceed allocation count")


@dataclass(frozen=True, slots=True)
class LeaseLlmAdmittedWorkItems:
    lease_repository: WorkItemLeaseRepositoryPort
    capacity_policy: CapacityAdmissionPolicy
    llm_capacity_projector: ProjectLlmCapacityToCapacityRuntime

    async def execute(
        self,
        command: LeaseLlmAdmittedWorkItemsCommand,
    ) -> LeaseLlmAdmittedWorkItemsResult:
        projection = self.llm_capacity_projector.execute(
            LlmCapacityProjectionCommand(
                profile=command.profile,
                accounts=command.accounts,
                requested_items=command.requested_items,
            ),
        )

        lease_result = await LeaseAdmittedWorkItems(
            repository=self.lease_repository,
            capacity_policy=self.capacity_policy,
        ).execute(
            LeaseAdmittedWorkItemsCommand(
                work_kind=command.work_kind,
                work_class=CapacityWorkClass.LLM_BOUND,
                capacity_needs=projection.capacity_needs,
                capacity_snapshot=projection.capacity_snapshot,
                requested_items=projection.requested_items,
                worker=command.worker,
                lease_token_prefix=command.lease_token_prefix,
                lease_expires_at=command.lease_expires_at,
                now=command.now,
            ),
        )

        assigned = tuple(
            LlmAdmittedLeasedWorkItem(
                leased=leased_record,
                allocation=projection.allocations[index],
            )
            for index, leased_record in enumerate(lease_result.leased)
        )
        return LeaseLlmAdmittedWorkItemsResult(
            llm_capacity_projection=projection,
            lease_result=lease_result,
            leased=assigned,
        )


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
