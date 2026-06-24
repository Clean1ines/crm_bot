from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionAdmitterPort,
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionAdmittedItemSummary,
    CapacityAdmissionCapacityReservationSummary,
    CapacityAdmissionFrontendEventSummary,
    CapacityAdmissionLaneSummary,
    CapacityAdmissionProjectionLeaseSummary,
    CapacityAdmissionStartedAttemptSummary,
    CapacityWindowAdmissionLogEvent,
    CapacityWindowAdmissionPassResult,
    CapacityWindowAdmissionSkippedReason,
)
from src.contexts.capacity_admission_queue.application.lease_selected_capacity_admission_work_item import (
    LeaseSelectedCapacityAdmissionWorkItem,
    LeaseSelectedCapacityAdmissionWorkItemCommand,
    TargetedExecutionWorkItemLeasePort,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
    CapacityAdmissionWindowBudget,
    CapacityAdmissionWorkItemSelectorPort,
    SelectCapacityAdmissionWorkItem,
    SelectCapacityAdmissionWorkItemCommand,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(frozen=True, slots=True)
class CapacityWindowAdmissionReservationResult:
    reserved: bool
    budget_after: CapacityAdmissionWindowBudget
    reservation_summary: CapacityAdmissionCapacityReservationSummary | None = None
    skipped_reason: CapacityWindowAdmissionSkippedReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reserved, bool):
            raise TypeError("reserved must be bool")
        if not isinstance(self.budget_after, CapacityAdmissionWindowBudget):
            raise TypeError("budget_after must be CapacityAdmissionWindowBudget")
        if self.reservation_summary is not None and not isinstance(
            self.reservation_summary,
            CapacityAdmissionCapacityReservationSummary,
        ):
            raise TypeError(
                "reservation_summary must be CapacityAdmissionCapacityReservationSummary"
            )
        if self.skipped_reason is not None and not isinstance(
            self.skipped_reason,
            CapacityWindowAdmissionSkippedReason,
        ):
            raise TypeError(
                "skipped_reason must be CapacityWindowAdmissionSkippedReason"
            )
        if self.reserved and self.reservation_summary is None:
            raise ValueError("reserved result must include reservation_summary")
        if self.reserved and self.skipped_reason is not None:
            raise ValueError("reserved result must not include skipped_reason")
        if not self.reserved and self.skipped_reason is None:
            raise ValueError("not reserved result must include skipped_reason")
        if not self.reserved and self.reservation_summary is not None:
            raise ValueError("not reserved result must not include reservation_summary")


class CapacityWindowAdmissionReservationPort(Protocol):
    async def reserve_capacity_for_selected_work_item(
        self,
        *,
        reservation_ref: str,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        budget: CapacityAdmissionWindowBudget,
        now: datetime,
        expires_at: datetime,
    ) -> CapacityWindowAdmissionReservationResult:
        """Reserve capacity for a selected projection candidate."""


@dataclass(frozen=True, slots=True)
class CapacityWindowAdmissionExecutionReference:
    work_item_id: str
    attempt_id: str | None = None
    attempt_number: int | None = None
    execute_command_ref: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.work_item_id, "work_item_id")
        if self.attempt_id is not None:
            _require_non_empty_text(self.attempt_id, "attempt_id")
        if self.attempt_number is not None:
            _require_positive_int(self.attempt_number, "attempt_number")
        if self.execute_command_ref is not None:
            _require_non_empty_text(self.execute_command_ref, "execute_command_ref")

        has_attempt = self.attempt_id is not None or self.attempt_number is not None
        has_command = self.execute_command_ref is not None

        if has_attempt and has_command:
            raise ValueError(
                "execution reference must contain either attempt or command ref"
            )
        if not has_attempt and not has_command:
            raise ValueError("execution reference must contain attempt or command ref")
        if has_attempt and (self.attempt_id is None or self.attempt_number is None):
            raise ValueError("attempt execution reference requires id and number")

    def to_started_attempt_summary(
        self,
    ) -> CapacityAdmissionStartedAttemptSummary | None:
        if self.attempt_id is None or self.attempt_number is None:
            return None
        return CapacityAdmissionStartedAttemptSummary(
            attempt_id=self.attempt_id,
            work_item_id=self.work_item_id,
            attempt_number=self.attempt_number,
        )


class CapacityWindowAdmissionExecutionBoundaryPort(Protocol):
    async def start_or_append_execution(
        self,
        *,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        leased_work_item: LeasedWorkItemRecord,
        projection_lease: CapacityAdmissionProjectionLeaseResult,
        capacity_reservation: CapacityAdmissionCapacityReservationSummary,
        now: datetime,
    ) -> CapacityWindowAdmissionExecutionReference:
        """Start attempt or return an explicit execute command reference."""


class CapacityWindowAdmissionActiveLeaseInspectorPort(Protocol):
    async def has_active_leased_work(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        now: datetime,
    ) -> bool:
        """Return whether the lane still has active leased work."""


@dataclass(frozen=True, slots=True)
class CapacityWindowAdmissionPassCommand:
    workflow_run_id: str
    phase: str
    operation_key: str
    lane_key: CapacityAdmissionLaneKey
    budget: CapacityAdmissionWindowBudget
    worker: WorkerRef
    lease_token_prefix: str
    lease_expires_at: datetime
    now: datetime
    max_admitted_items: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.phase, "phase")
        _require_non_empty_text(self.operation_key, "operation_key")
        if not isinstance(self.lane_key, CapacityAdmissionLaneKey):
            raise TypeError("lane_key must be CapacityAdmissionLaneKey")
        if not isinstance(self.budget, CapacityAdmissionWindowBudget):
            raise TypeError("budget must be CapacityAdmissionWindowBudget")
        if not isinstance(self.worker, WorkerRef):
            raise TypeError("worker must be WorkerRef")
        _require_non_empty_text(self.lease_token_prefix, "lease_token_prefix")
        _require_timezone_aware(self.lease_expires_at, "lease_expires_at")
        _require_timezone_aware(self.now, "now")
        if self.lease_expires_at <= self.now:
            raise ValueError("lease_expires_at must be after now")
        _require_positive_int(self.max_admitted_items, "max_admitted_items")


@dataclass(frozen=True, slots=True)
class CapacityWindowAdmissionPass:
    selector: CapacityAdmissionWorkItemSelectorPort
    execution_lease_repository: TargetedExecutionWorkItemLeasePort
    projection_admitter: CapacityAdmissionProjectionAdmitterPort
    capacity_reservation: CapacityWindowAdmissionReservationPort
    execution_boundary: CapacityWindowAdmissionExecutionBoundaryPort
    active_lease_inspector: CapacityWindowAdmissionActiveLeaseInspectorPort

    async def execute(
        self,
        command: CapacityWindowAdmissionPassCommand,
    ) -> CapacityWindowAdmissionPassResult:
        budget = command.budget
        admitted_items: list[CapacityAdmissionAdmittedItemSummary] = []
        projection_leases: list[CapacityAdmissionProjectionLeaseSummary] = []
        capacity_reservations: list[CapacityAdmissionCapacityReservationSummary] = []
        started_attempts: list[CapacityAdmissionStartedAttemptSummary] = []
        execute_command_refs: list[str] = []

        for admission_index in range(command.max_admitted_items):
            selection = await SelectCapacityAdmissionWorkItem(self.selector).execute(
                SelectCapacityAdmissionWorkItemCommand(
                    lane_key=command.lane_key,
                    budget=budget,
                )
            )
            selected_work_item = selection.selected_work_item
            if selected_work_item is None:
                skipped_reason = await self._selection_skipped_reason(
                    command=command,
                    selection_skipped_reason=selection.skipped_reason,
                )
                if admitted_items:
                    return self._admitted_result(
                        command=command,
                        admitted_items=tuple(admitted_items),
                        projection_leases=tuple(projection_leases),
                        capacity_reservations=tuple(capacity_reservations),
                        started_attempts=tuple(started_attempts),
                        execute_command_refs=tuple(execute_command_refs),
                    )
                return self._skipped_result(command, skipped_reason)

            reservation_ref = _reservation_ref(
                prefix=command.lease_token_prefix,
                admission_index=admission_index,
                work_item_id=selected_work_item.work_item_id,
            )
            reservation = (
                await self.capacity_reservation.reserve_capacity_for_selected_work_item(
                    reservation_ref=reservation_ref,
                    selected_work_item=selected_work_item,
                    budget=budget,
                    now=command.now,
                    expires_at=command.lease_expires_at,
                )
            )
            if not reservation.reserved:
                skipped_reason = (
                    reservation.skipped_reason
                    or CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED
                )
                if admitted_items:
                    return self._admitted_result(
                        command=command,
                        admitted_items=tuple(admitted_items),
                        projection_leases=tuple(projection_leases),
                        capacity_reservations=tuple(capacity_reservations),
                        started_attempts=tuple(started_attempts),
                        execute_command_refs=tuple(execute_command_refs),
                    )
                return self._skipped_result(command, skipped_reason)

            lease_result = await LeaseSelectedCapacityAdmissionWorkItem(
                execution_lease_repository=self.execution_lease_repository,
                projection_admitter=self.projection_admitter,
            ).execute(
                LeaseSelectedCapacityAdmissionWorkItemCommand(
                    selected_work_item=selected_work_item,
                    worker=command.worker,
                    lease_token=_lease_token(
                        prefix=command.lease_token_prefix,
                        admission_index=admission_index,
                        work_item_id=selected_work_item.work_item_id,
                    ),
                    lease_expires_at=command.lease_expires_at,
                    now=command.now,
                )
            )
            if not lease_result.leased:
                skipped_reason = _lease_skipped_reason(lease_result.skipped_reason)
                if admitted_items:
                    return self._admitted_result(
                        command=command,
                        admitted_items=tuple(admitted_items),
                        projection_leases=tuple(projection_leases),
                        capacity_reservations=tuple(capacity_reservations),
                        started_attempts=tuple(started_attempts),
                        execute_command_refs=tuple(execute_command_refs),
                    )
                return self._skipped_result(command, skipped_reason)

            if lease_result.execution_lease is None:
                raise RuntimeError("leased result must include execution_lease")
            if lease_result.projection_lease is None:
                raise RuntimeError("leased result must include projection_lease")
            if reservation.reservation_summary is None:
                raise RuntimeError("reserved result must include reservation_summary")
            reservation_summary = reservation.reservation_summary

            execution_reference = (
                await self.execution_boundary.start_or_append_execution(
                    selected_work_item=selected_work_item,
                    leased_work_item=lease_result.execution_lease,
                    projection_lease=lease_result.projection_lease,
                    capacity_reservation=reservation_summary,
                    now=command.now,
                )
            )

            admitted_items.append(_admitted_item_summary(selected_work_item))
            projection_leases.append(
                _projection_lease_summary(lease_result.projection_lease)
            )
            capacity_reservations.append(reservation_summary)

            started_attempt = execution_reference.to_started_attempt_summary()
            if started_attempt is not None:
                started_attempts.append(started_attempt)
            elif execution_reference.execute_command_ref is not None:
                execute_command_refs.append(execution_reference.execute_command_ref)
            else:
                raise RuntimeError("execution boundary returned invalid reference")

            budget = reservation.budget_after

        if admitted_items:
            return self._admitted_result(
                command=command,
                admitted_items=tuple(admitted_items),
                projection_leases=tuple(projection_leases),
                capacity_reservations=tuple(capacity_reservations),
                started_attempts=tuple(started_attempts),
                execute_command_refs=tuple(execute_command_refs),
            )

        return self._skipped_result(
            command,
            CapacityWindowAdmissionSkippedReason.NO_FITTING_WORK_ITEM,
        )

    async def _selection_skipped_reason(
        self,
        *,
        command: CapacityWindowAdmissionPassCommand,
        selection_skipped_reason: str | None,
    ) -> CapacityWindowAdmissionSkippedReason:
        if selection_skipped_reason == "capacity_exhausted":
            return CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED
        if selection_skipped_reason == "no_fitting_work_item":
            has_active_leased_work = (
                await self.active_lease_inspector.has_active_leased_work(
                    lane_key=command.lane_key,
                    now=command.now,
                )
            )
            if has_active_leased_work:
                return CapacityWindowAdmissionSkippedReason.ACTIVE_LEASED_WAIT
            return CapacityWindowAdmissionSkippedReason.NO_FITTING_WORK_ITEM
        return CapacityWindowAdmissionSkippedReason.NO_FITTING_WORK_ITEM

    def _admitted_result(
        self,
        *,
        command: CapacityWindowAdmissionPassCommand,
        admitted_items: tuple[CapacityAdmissionAdmittedItemSummary, ...],
        projection_leases: tuple[CapacityAdmissionProjectionLeaseSummary, ...],
        capacity_reservations: tuple[CapacityAdmissionCapacityReservationSummary, ...],
        started_attempts: tuple[CapacityAdmissionStartedAttemptSummary, ...],
        execute_command_refs: tuple[str, ...],
    ) -> CapacityWindowAdmissionPassResult:
        return CapacityWindowAdmissionPassResult(
            workflow_run_id=command.workflow_run_id,
            phase=command.phase,
            operation_key=command.operation_key,
            work_kind=command.lane_key.work_kind,
            lane=_lane_summary(command.lane_key),
            admitted_items=admitted_items,
            projection_leases=projection_leases,
            capacity_reservations=capacity_reservations,
            started_attempts=started_attempts,
            appended_execute_command_refs=execute_command_refs,
            frontend_event_summary=CapacityAdmissionFrontendEventSummary(
                event_kind="capacity_admission_pass_completed",
                workflow_run_id=command.workflow_run_id,
                phase=command.phase,
                operation_key=command.operation_key,
                work_kind=command.lane_key.work_kind,
                lane=_lane_summary(command.lane_key),
                admitted_count=len(admitted_items),
                started_attempt_count=len(started_attempts),
                work_item_ids=tuple(item.work_item_id for item in admitted_items),
                attempt_ids=tuple(attempt.attempt_id for attempt in started_attempts),
                projection_event_ids=tuple(
                    projection.event_id for projection in projection_leases
                ),
                occurred_at=command.now,
            ),
            log_event=CapacityWindowAdmissionLogEvent.PASS_COMPLETED,
        )

    def _skipped_result(
        self,
        command: CapacityWindowAdmissionPassCommand,
        skipped_reason: CapacityWindowAdmissionSkippedReason,
    ) -> CapacityWindowAdmissionPassResult:
        return CapacityWindowAdmissionPassResult(
            workflow_run_id=command.workflow_run_id,
            phase=command.phase,
            operation_key=command.operation_key,
            work_kind=command.lane_key.work_kind,
            lane=_lane_summary(command.lane_key),
            skipped_reason=skipped_reason,
            frontend_event_summary=CapacityAdmissionFrontendEventSummary(
                event_kind="capacity_admission_pass_skipped",
                workflow_run_id=command.workflow_run_id,
                phase=command.phase,
                operation_key=command.operation_key,
                work_kind=command.lane_key.work_kind,
                lane=_lane_summary(command.lane_key),
                admitted_count=0,
                started_attempt_count=0,
                skipped_reason=skipped_reason,
                occurred_at=command.now,
            ),
            log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
        )


def _admitted_item_summary(
    selected_work_item: CapacityAdmissionSelectableWorkItem,
) -> CapacityAdmissionAdmittedItemSummary:
    estimated_input_tokens = (
        selected_work_item.estimated_input_tokens
        if selected_work_item.estimated_input_tokens is not None
        else selected_work_item.reserved_total_tokens
    )
    estimated_output_tokens = (
        selected_work_item.estimated_output_tokens
        if selected_work_item.estimated_output_tokens is not None
        else 0
    )
    effective_output_cap_tokens = (
        selected_work_item.effective_output_cap_tokens
        if selected_work_item.effective_output_cap_tokens is not None
        else max(estimated_output_tokens, 1)
    )

    return CapacityAdmissionAdmittedItemSummary(
        work_item_id=selected_work_item.work_item_id,
        lane=_lane_summary(selected_work_item.lane_key),
        selection_kind=_selection_kind(selected_work_item),
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        effective_output_cap_tokens=effective_output_cap_tokens,
        reserved_total_tokens=selected_work_item.reserved_total_tokens,
    )


def _projection_lease_summary(
    projection_lease: CapacityAdmissionProjectionLeaseResult,
) -> CapacityAdmissionProjectionLeaseSummary:
    return CapacityAdmissionProjectionLeaseSummary(
        work_item_id=projection_lease.work_item_id,
        lane=_lane_summary(projection_lease.lane_key),
        previous_status=projection_lease.previous_status,
        status=projection_lease.status,
        event_id=projection_lease.event_id,
    )


def _lane_summary(lane_key: CapacityAdmissionLaneKey) -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind=lane_key.work_kind,
        provider=lane_key.provider,
        account_ref=lane_key.account_ref,
        model_ref=lane_key.model_ref,
    )


def _selection_kind(selected_work_item: CapacityAdmissionSelectableWorkItem) -> str:
    if selected_work_item.status == "retryable_failed":
        return "retryable"
    return "fresh"


def _lease_skipped_reason(
    skipped_reason: str | None,
) -> CapacityWindowAdmissionSkippedReason:
    if skipped_reason == "execution_work_item_not_leased":
        return CapacityWindowAdmissionSkippedReason.EXECUTION_LEASE_LOST
    if skipped_reason == "capacity_projection_not_admitted":
        return CapacityWindowAdmissionSkippedReason.PROJECTION_CONFLICT
    return CapacityWindowAdmissionSkippedReason.PROJECTION_CONFLICT


def _reservation_ref(
    *,
    prefix: str,
    admission_index: int,
    work_item_id: str,
) -> str:
    return f"{prefix}:{admission_index + 1}:{work_item_id}"


def _lease_token(
    *,
    prefix: str,
    admission_index: int,
    work_item_id: str,
) -> LeaseToken:
    return LeaseToken(f"{prefix}:{admission_index + 1}:{work_item_id}")


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
