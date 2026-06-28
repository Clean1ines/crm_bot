from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionLease,
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_pass import (
    CapacityWindowAdmissionCapacityPreviewResult,
    CapacityWindowAdmissionExecutionReference,
    CapacityWindowAdmissionPass,
    CapacityWindowAdmissionPassCommand,
    CapacityWindowAdmissionReservationResult,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionCapacityReservationSummary,
    CapacityAdmissionLaneSummary,
    CapacityWindowAdmissionSkippedReason,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
    CapacityAdmissionWindowBudget,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(slots=True)
class SelectorCall:
    status: str
    max_required_window_tokens: int


class FakeSelector:
    def __init__(
        self,
        *,
        retryable_failed_items: tuple[CapacityAdmissionSelectableWorkItem, ...] = (),
        ready_items: tuple[CapacityAdmissionSelectableWorkItem, ...] = (),
    ) -> None:
        self.retryable_failed_items = list(retryable_failed_items)
        self.ready_items = list(ready_items)
        self.calls: list[SelectorCall] = []

    async def select_first_retryable_failed_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        self.calls.append(
            SelectorCall(
                status="retryable_failed",
                max_required_window_tokens=max_required_window_tokens,
            )
        )
        return self._pop_fitting(
            self.retryable_failed_items, max_required_window_tokens
        )

    async def select_first_ready_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        self.calls.append(
            SelectorCall(
                status="ready",
                max_required_window_tokens=max_required_window_tokens,
            )
        )
        return self._pop_fitting(self.ready_items, max_required_window_tokens)

    def _pop_fitting(
        self,
        items: list[CapacityAdmissionSelectableWorkItem],
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        for index, item in enumerate(items):
            if item.required_window_tokens <= max_required_window_tokens:
                return items.pop(index)
        return None


class FakeExecutionLeaseRepository:
    def __init__(self, *, lost_work_item_ids: tuple[str, ...] = ()) -> None:
        self.lost_work_item_ids = set(lost_work_item_ids)
        self.leased_work_item_ids: list[str] = []

    async def lease_due_work_item_by_id(
        self,
        *,
        work_kind: WorkKind,
        work_item_id: str,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None:
        if work_item_id in self.lost_work_item_ids:
            return None
        self.leased_work_item_ids.append(work_item_id)
        return LeasedWorkItemRecord(
            work_item=WorkItem(
                work_item_id=work_item_id,
                work_kind=work_kind,
                status=WorkItemStatus.LEASED,
                attempt_count=1,
                leased_by=worker,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
            ),
            schedule_payload={
                "workflow_run_id": "workflow-run-1",
                "work_item_id": work_item_id,
            },
        )


class FakeProjectionAdmitter:
    def __init__(self, *, conflict_work_item_ids: tuple[str, ...] = ()) -> None:
        self.conflict_work_item_ids = set(conflict_work_item_ids)
        self.leased_work_item_ids: list[str] = []

    async def admit_projection_work_item(
        self,
        lease: CapacityAdmissionProjectionLease,
    ) -> CapacityAdmissionProjectionLeaseResult | None:
        if lease.work_item_id in self.conflict_work_item_ids:
            return None
        self.leased_work_item_ids.append(lease.work_item_id)
        return CapacityAdmissionProjectionLeaseResult(
            work_item_id=lease.work_item_id,
            lane_key=lease.lane_key,
            previous_status="retryable_failed"
            if lease.work_item_id.endswith("retry")
            else "ready",
            status="leased",
            event_id=uuid4(),
        )


class FakeCapacityReservation:
    def __init__(self, *, deny_after_count: int | None = None) -> None:
        self.deny_after_count = deny_after_count
        self.calls = 0

    async def preview_capacity_for_selected_work_item(
        self,
        *,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        execution_lane_key: CapacityAdmissionLaneKey,
        budget: CapacityAdmissionWindowBudget,
        now: datetime,
    ) -> CapacityWindowAdmissionCapacityPreviewResult:
        del selected_work_item, execution_lane_key, now
        return CapacityWindowAdmissionCapacityPreviewResult(
            capacity_available=True,
            budget_after_active_reservations=budget,
        )

    async def reserve_capacity_for_selected_work_item(
        self,
        *,
        attempt_id: str,
        reservation_ref: str,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        execution_lane_key: CapacityAdmissionLaneKey,
        budget: CapacityAdmissionWindowBudget,
        now: datetime,
        expires_at: datetime,
    ) -> CapacityWindowAdmissionReservationResult:
        del attempt_id
        self.calls += 1
        if self.deny_after_count is not None and self.calls > self.deny_after_count:
            return CapacityWindowAdmissionReservationResult(
                reserved=False,
                budget_after=budget,
                skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            )
        return CapacityWindowAdmissionReservationResult(
            reserved=True,
            reservation_summary=CapacityAdmissionCapacityReservationSummary(
                reservation_ref=reservation_ref,
                work_item_id=selected_work_item.work_item_id,
                lane=CapacityAdmissionLaneSummary(
                    work_kind=execution_lane_key.work_kind,
                    provider=execution_lane_key.provider,
                    account_ref=execution_lane_key.account_ref,
                    model_ref=execution_lane_key.model_ref,
                ),
                reserved_requests=1,
                reserved_tokens=selected_work_item.required_window_tokens,
                expires_at=expires_at,
            ),
            budget_after=CapacityAdmissionWindowBudget(
                remaining_requests=budget.remaining_requests - 1,
                remaining_tokens=budget.remaining_tokens
                - selected_work_item.required_window_tokens,
                remaining_daily_requests=budget.remaining_daily_requests - 1,
                remaining_daily_tokens=budget.remaining_daily_tokens
                - selected_work_item.required_window_tokens,
            ),
        )


class FakeExecutionBoundary:
    def __init__(self, *, append_command: bool = False) -> None:
        self.append_command = append_command
        self.started_work_item_ids: list[str] = []

    async def start_or_append_execution(
        self,
        *,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        execution_lane_key: CapacityAdmissionLaneKey,
        leased_work_item: LeasedWorkItemRecord,
        projection_lease: CapacityAdmissionProjectionLeaseResult,
        capacity_reservation: CapacityAdmissionCapacityReservationSummary,
        now: datetime,
    ) -> CapacityWindowAdmissionExecutionReference:
        del execution_lane_key
        self.started_work_item_ids.append(selected_work_item.work_item_id)
        if self.append_command:
            return CapacityWindowAdmissionExecutionReference(
                work_item_id=selected_work_item.work_item_id,
                execute_command_ref=f"execute:{selected_work_item.work_item_id}",
            )
        return CapacityWindowAdmissionExecutionReference(
            work_item_id=selected_work_item.work_item_id,
            attempt_id=leased_work_item.work_item.lease_token.value,
            attempt_number=1,
        )


class FakeActiveLeaseInspector:
    def __init__(self, *, active: bool) -> None:
        self.active = active

    async def has_active_leased_work(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        now: datetime,
    ) -> bool:
        return self.active


def _shared_lane() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        provider="groq",
        account_ref=None,
        model_ref="qwen/qwen3-32b",
    )


def _execution_lane() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )


def _budget() -> CapacityAdmissionWindowBudget:
    return CapacityAdmissionWindowBudget(
        remaining_requests=10,
        remaining_tokens=10_000,
        remaining_daily_requests=100,
        remaining_daily_tokens=100_000,
    )


def _command() -> CapacityWindowAdmissionPassCommand:
    now = datetime.now(timezone.utc)
    return CapacityWindowAdmissionPassCommand(
        workflow_run_id="workflow-run-1",
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        operation_key="prepare_claim_builder_dispatch",
        lane_key=_shared_lane(),
        execution_lane_key=_execution_lane(),
        budget=_budget(),
        worker=WorkerRef("capacity-admission-worker"),
        lease_token_prefix="capacity-admission:workflow-run-1",
        lease_expires_at=now + timedelta(minutes=2),
        now=now,
        max_admitted_items=10,
    )


def _item(
    work_item_id: str,
    *,
    status: str = "ready",
    required_window_tokens: int = 150,
) -> CapacityAdmissionSelectableWorkItem:
    if status == "retryable_failed":
        return CapacityAdmissionSelectableWorkItem(
            work_item_id=work_item_id,
            lane_key=_shared_lane(),
            status="retryable_failed",
            required_window_tokens=required_window_tokens,
            input_tokens=100,
            artifact_tokens=40,
        )
    return CapacityAdmissionSelectableWorkItem(
        work_item_id=work_item_id,
        lane_key=_shared_lane(),
        status="ready",
        required_window_tokens=required_window_tokens,
        input_tokens=100,
        artifact_tokens=40,
    )


def _pass(
    *,
    selector: FakeSelector,
    execution_lease_repository: FakeExecutionLeaseRepository | None = None,
    projection_admitter: FakeProjectionAdmitter | None = None,
    reservation: FakeCapacityReservation | None = None,
    execution_boundary: FakeExecutionBoundary | None = None,
    active_lease_inspector: FakeActiveLeaseInspector | None = None,
) -> CapacityWindowAdmissionPass:
    return CapacityWindowAdmissionPass(
        selector=selector,
        execution_lease_repository=execution_lease_repository
        or FakeExecutionLeaseRepository(),
        projection_admitter=projection_admitter or FakeProjectionAdmitter(),
        capacity_reservation=reservation or FakeCapacityReservation(),
        execution_boundary=execution_boundary or FakeExecutionBoundary(),
        active_lease_inspector=active_lease_inspector
        or FakeActiveLeaseInspector(active=False),
    )


@pytest.mark.asyncio
async def test_pass_admits_retryable_before_ready_and_returns_started_attempts() -> (
    None
):
    selector = FakeSelector(
        retryable_failed_items=(_item("work-item-retry", status="retryable_failed"),),
        ready_items=(_item("work-item-ready"),),
    )

    result = await _pass(selector=selector).execute(_command())

    assert result.skipped is False
    assert result.admitted_count == 2
    assert [item.work_item_id for item in result.admitted_items] == [
        "work-item-retry",
        "work-item-ready",
    ]
    assert [item.selection_kind for item in result.admitted_items] == [
        "retryable",
        "fresh",
    ]
    assert [attempt.work_item_id for attempt in result.started_attempts] == [
        "work-item-retry",
        "work-item-ready",
    ]
    assert result.frontend_event_summary is not None
    assert result.frontend_event_summary.admitted_count == 2
    assert result.capacity_reservations[0].reservation_ref.endswith("work-item-retry")

    assert result.lane.account_ref is None
    assert all(item.lane.account_ref is None for item in result.admitted_items)
    assert all(lease.lane.account_ref is None for lease in result.projection_leases)
    assert all(
        reservation.lane.account_ref == "groq-account-1"
        for reservation in result.capacity_reservations
    )


@pytest.mark.asyncio
async def test_pass_returns_capacity_exhausted_without_selector_calls() -> None:
    command = _command()
    exhausted_command = CapacityWindowAdmissionPassCommand(
        workflow_run_id=command.workflow_run_id,
        phase=command.phase,
        operation_key=command.operation_key,
        lane_key=command.lane_key,
        execution_lane_key=command.execution_lane_key,
        budget=CapacityAdmissionWindowBudget(
            remaining_requests=0,
            remaining_tokens=10,
            remaining_daily_requests=10,
            remaining_daily_tokens=10,
        ),
        worker=command.worker,
        lease_token_prefix=command.lease_token_prefix,
        lease_expires_at=command.lease_expires_at,
        now=command.now,
        max_admitted_items=10,
    )
    selector = FakeSelector()

    result = await _pass(selector=selector).execute(exhausted_command)

    assert result.skipped is True
    assert (
        result.skipped_reason is CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED
    )
    assert selector.calls == []


@pytest.mark.asyncio
async def test_pass_maps_no_fitting_work_to_active_leased_wait_when_lane_has_leases() -> (
    None
):
    result = await _pass(
        selector=FakeSelector(),
        active_lease_inspector=FakeActiveLeaseInspector(active=True),
    ).execute(_command())

    assert result.skipped is True
    assert (
        result.skipped_reason is CapacityWindowAdmissionSkippedReason.ACTIVE_LEASED_WAIT
    )


@pytest.mark.asyncio
async def test_pass_maps_execution_lease_loss() -> None:
    result = await _pass(
        selector=FakeSelector(ready_items=(_item("work-item-lost"),)),
        execution_lease_repository=FakeExecutionLeaseRepository(
            lost_work_item_ids=("work-item-lost",)
        ),
    ).execute(_command())

    assert result.skipped is True
    assert (
        result.skipped_reason
        is CapacityWindowAdmissionSkippedReason.EXECUTION_LEASE_LOST
    )


@pytest.mark.asyncio
async def test_pass_maps_projection_conflict() -> None:
    result = await _pass(
        selector=FakeSelector(ready_items=(_item("work-item-conflict"),)),
        projection_admitter=FakeProjectionAdmitter(
            conflict_work_item_ids=("work-item-conflict",)
        ),
    ).execute(_command())

    assert result.skipped is True
    assert (
        result.skipped_reason
        is CapacityWindowAdmissionSkippedReason.PROJECTION_CONFLICT
    )


@pytest.mark.asyncio
async def test_pass_supports_append_execute_command_boundary() -> None:
    result = await _pass(
        selector=FakeSelector(ready_items=(_item("work-item-command"),)),
        execution_boundary=FakeExecutionBoundary(append_command=True),
    ).execute(_command())

    assert result.skipped is False
    assert result.started_attempts == ()
    assert result.appended_execute_command_refs == ("execute:work-item-command",)


@pytest.mark.asyncio
async def test_pass_stops_at_safety_cap() -> None:
    command = _command()
    capped_command = CapacityWindowAdmissionPassCommand(
        workflow_run_id=command.workflow_run_id,
        phase=command.phase,
        operation_key=command.operation_key,
        lane_key=command.lane_key,
        execution_lane_key=command.execution_lane_key,
        budget=command.budget,
        worker=command.worker,
        lease_token_prefix=command.lease_token_prefix,
        lease_expires_at=command.lease_expires_at,
        now=command.now,
        max_admitted_items=1,
    )

    result = await _pass(
        selector=FakeSelector(
            ready_items=(_item("work-item-1"), _item("work-item-2")),
        )
    ).execute(capped_command)

    assert result.skipped is False
    assert result.admitted_count == 1
    assert result.admitted_items[0].work_item_id == "work-item-1"


@pytest.mark.asyncio
async def test_pass_stops_when_reservation_denies_capacity() -> None:
    result = await _pass(
        selector=FakeSelector(ready_items=(_item("work-item-1"),)),
        reservation=FakeCapacityReservation(deny_after_count=0),
    ).execute(_command())

    assert result.skipped is True
    assert (
        result.skipped_reason is CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED
    )
