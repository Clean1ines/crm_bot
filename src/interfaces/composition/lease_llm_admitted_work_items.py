from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.contexts.capacity_runtime.domain.capacity_decision import CapacityWorkClass
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
    LeasedWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
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
    LlmCapacityProjectionResult,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
    SelectActiveLlmModelCapacityCommand,
    SelectActiveLlmModelCapacityResult,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelExecutionSettings,
    LlmModelRouteCatalog,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_window_workflow_events import (
    admission_selection_kind_from_work_item_status,
)


CapacityWindowAdmissionSelectionKind = Literal["fresh", "retryable"]


@dataclass(frozen=True, slots=True)
class LlmAdmittedLeasedWorkItem:
    leased: LeasedWorkItemRecord
    allocation: LlmCapacityAllocationSlot
    execution_settings: LlmModelExecutionSettings
    selection_kind: CapacityWindowAdmissionSelectionKind
    schedule_payload_override: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.leased, LeasedWorkItemRecord):
            raise TypeError("leased must be LeasedWorkItemRecord")
        if not isinstance(self.allocation, LlmCapacityAllocationSlot):
            raise TypeError("allocation must be LlmCapacityAllocationSlot")
        if not isinstance(self.execution_settings, LlmModelExecutionSettings):
            raise TypeError("execution_settings must be LlmModelExecutionSettings")
        if self.selection_kind not in {"fresh", "retryable"}:
            raise ValueError("selection_kind must be fresh or retryable")
        if self.schedule_payload_override is not None and not isinstance(
            self.schedule_payload_override,
            Mapping,
        ):
            raise TypeError("schedule_payload_override must be Mapping when provided")

    def admitted_schedule_payload(self) -> dict[str, object]:
        if self.schedule_payload_override is None:
            return dict(self.leased.schedule_payload)
        return dict(self.schedule_payload_override)

    def to_dispatch_payload(self) -> dict[str, object]:
        return {
            "work_item_id": self.leased.work_item.work_item_id,
            "schedule_payload": self.admitted_schedule_payload(),
            "llm_allocation": self.allocation.to_payload(),
            "llm_execution_settings": self.execution_settings.to_provider_options(),
        }


def llm_admitted_leased_work_item_from_pre_lease_status(
    *,
    leased: LeasedWorkItemRecord,
    allocation: LlmCapacityAllocationSlot,
    execution_settings: LlmModelExecutionSettings,
    pre_lease_status: WorkItemStatus,
    schedule_payload_override: Mapping[str, object] | None = None,
) -> LlmAdmittedLeasedWorkItem:
    """Bind admission selection_kind to the exact pre-lease work item status."""

    return LlmAdmittedLeasedWorkItem(
        leased=leased,
        allocation=allocation,
        execution_settings=execution_settings,
        selection_kind=admission_selection_kind_from_work_item_status(
            pre_lease_status,
        ),
        schedule_payload_override=schedule_payload_override,
    )


def admission_selection_kinds_from_due_records(
    due_records: tuple[DueWorkItemRecord, ...],
) -> dict[str, CapacityWindowAdmissionSelectionKind]:
    return {
        record.work_item.work_item_id: admission_selection_kind_from_work_item_status(
            record.work_item.status,
        )
        for record in due_records
    }


@dataclass(frozen=True, slots=True)
class LeaseLlmAdmittedWorkItemsCommand:
    work_kind: WorkKind
    profile: LlmTaskCapacityProfile
    account_capacities: tuple[LlmProviderAccountCapacity, ...]
    active_model_ref: str
    requested_items: int
    worker: WorkerRef
    lease_token_prefix: str
    lease_expires_at: datetime
    now: datetime
    pre_lease_due_records: tuple[DueWorkItemRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        if not isinstance(self.profile, LlmTaskCapacityProfile):
            raise TypeError("profile must be LlmTaskCapacityProfile")
        if not isinstance(self.account_capacities, tuple):
            raise TypeError("account_capacities must be tuple")
        if not self.account_capacities:
            raise ValueError("account_capacities must be non-empty")
        for account in self.account_capacities:
            if not isinstance(account, LlmProviderAccountCapacity):
                raise TypeError(
                    "account_capacities must contain LlmProviderAccountCapacity",
                )
        _require_non_empty_text(self.active_model_ref, field_name="active_model_ref")
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
        if not isinstance(self.pre_lease_due_records, tuple):
            raise TypeError("pre_lease_due_records must be tuple")
        for record in self.pre_lease_due_records:
            if not isinstance(record, DueWorkItemRecord):
                raise TypeError(
                    "pre_lease_due_records must contain DueWorkItemRecord",
                )


@dataclass(frozen=True, slots=True)
class LeaseLlmAdmittedWorkItemsResult:
    active_model_capacity_selection: SelectActiveLlmModelCapacityResult
    lease_result: LeaseAdmittedWorkItemsResult
    leased: tuple[LlmAdmittedLeasedWorkItem, ...]

    @property
    def llm_capacity_projection(self) -> LlmCapacityProjectionResult:
        return self.active_model_capacity_selection.projection

    def __post_init__(self) -> None:
        if not isinstance(
            self.active_model_capacity_selection,
            SelectActiveLlmModelCapacityResult,
        ):
            raise TypeError(
                "active_model_capacity_selection must be "
                "SelectActiveLlmModelCapacityResult",
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
    active_model_capacity_selector: SelectActiveLlmModelCapacity
    route_catalog: LlmModelRouteCatalog

    def __post_init__(self) -> None:
        if not isinstance(self.route_catalog, LlmModelRouteCatalog):
            raise TypeError("route_catalog must be LlmModelRouteCatalog")

    async def execute(
        self,
        command: LeaseLlmAdmittedWorkItemsCommand,
    ) -> LeaseLlmAdmittedWorkItemsResult:
        selection = self.active_model_capacity_selector.execute(
            SelectActiveLlmModelCapacityCommand(
                profile=command.profile,
                account_capacities=command.account_capacities,
                active_model_ref=command.active_model_ref,
                requested_items=command.requested_items,
            ),
        )
        projection = selection.projection

        execution_settings = self.route_catalog.execution_settings_for_model_ref(
            command.active_model_ref,
        )

        selection_kind_by_work_item_id = admission_selection_kinds_from_due_records(
            command.pre_lease_due_records,
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
                execution_settings=execution_settings,
                selection_kind=_selection_kind_for_leased_record(
                    leased_record=leased_record,
                    selection_kind_by_work_item_id=selection_kind_by_work_item_id,
                ),
            )
            for index, leased_record in enumerate(lease_result.leased)
        )
        return LeaseLlmAdmittedWorkItemsResult(
            active_model_capacity_selection=selection,
            lease_result=lease_result,
            leased=assigned,
        )


def _selection_kind_for_leased_record(
    *,
    leased_record: LeasedWorkItemRecord,
    selection_kind_by_work_item_id: dict[str, CapacityWindowAdmissionSelectionKind],
) -> CapacityWindowAdmissionSelectionKind:
    work_item_id = leased_record.work_item.work_item_id
    selection_kind = selection_kind_by_work_item_id.get(work_item_id)
    if selection_kind is None:
        raise ValueError(
            "leased work item missing pre-lease admission selection_kind: "
            f"{work_item_id}"
        )
    return selection_kind


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
