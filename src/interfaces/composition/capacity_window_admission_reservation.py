from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_admission_queue.application.capacity_window_admission_pass import (
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
from src.contexts.llm_runtime.infrastructure.postgres.postgres_llm_route_capacity_reservation_repository import (
    LlmRouteCapacityReservation,
    LlmRouteCapacityReservationTotal,
)


class LlmRouteCapacityReservationRepositoryPort(Protocol):
    async def lock_route(
        self,
        *,
        provider: str,
        account_ref: str,
        model_ref: str,
    ) -> None: ...

    async def active_totals(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
        now: datetime,
    ) -> tuple[LlmRouteCapacityReservationTotal, ...]: ...

    async def reserve(self, reservation: LlmRouteCapacityReservation) -> None: ...


@dataclass(frozen=True, slots=True)
class ReserveLlmRouteCapacityForAdmission:
    reservation_repository: LlmRouteCapacityReservationRepositoryPort

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
        _require_non_empty_text(attempt_id, "attempt_id")
        _require_non_empty_text(reservation_ref, "reservation_ref")
        _require_timezone_aware(now, "now")
        _require_timezone_aware(expires_at, "expires_at")

        lane_key = execution_lane_key
        if lane_key.account_ref is None:
            raise ValueError("capacity admission reservation requires account_ref")
        if selected_work_item.lane_key.work_kind != lane_key.work_kind:
            raise ValueError("execution lane work_kind must match selected work item")
        if selected_work_item.lane_key.provider != lane_key.provider:
            raise ValueError("execution lane provider must match selected work item")
        if selected_work_item.lane_key.model_ref != lane_key.model_ref:
            raise ValueError("execution lane model_ref must match selected work item")

        await self.reservation_repository.lock_route(
            provider=lane_key.provider,
            account_ref=lane_key.account_ref,
            model_ref=lane_key.model_ref,
        )
        active_totals = await self.reservation_repository.active_totals(
            provider=lane_key.provider,
            account_refs=(lane_key.account_ref,),
            model_ref=lane_key.model_ref,
            now=now,
        )
        active_reserved_requests = sum(
            total.reserved_requests for total in active_totals
        )
        active_reserved_tokens = sum(total.reserved_tokens for total in active_totals)

        available_budget = _available_budget_after_active_reservations(
            budget,
            active_reserved_requests=active_reserved_requests,
            active_reserved_tokens=active_reserved_tokens,
        )
        if not available_budget.admits_any_work:
            return CapacityWindowAdmissionReservationResult(
                reserved=False,
                budget_after=available_budget,
                skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            )

        if (
            selected_work_item.required_window_tokens
            > available_budget.max_required_window_tokens
        ):
            return CapacityWindowAdmissionReservationResult(
                reserved=False,
                budget_after=available_budget,
                skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            )

        await self.reservation_repository.reserve(
            LlmRouteCapacityReservation(
                attempt_id=attempt_id,
                provider=lane_key.provider,
                account_ref=lane_key.account_ref,
                model_ref=lane_key.model_ref,
                reserved_requests=1,
                reserved_tokens=selected_work_item.required_window_tokens,
                expires_at=expires_at,
                created_at=now,
            )
        )

        budget_after = _budget_after_new_reservation(
            available_budget,
            reserved_tokens=selected_work_item.required_window_tokens,
        )
        return CapacityWindowAdmissionReservationResult(
            reserved=True,
            budget_after=budget_after,
            reservation_summary=CapacityAdmissionCapacityReservationSummary(
                reservation_ref=reservation_ref,
                work_item_id=selected_work_item.work_item_id,
                lane=CapacityAdmissionLaneSummary(
                    work_kind=lane_key.work_kind,
                    provider=lane_key.provider,
                    account_ref=lane_key.account_ref,
                    model_ref=lane_key.model_ref,
                ),
                reserved_requests=1,
                reserved_tokens=selected_work_item.required_window_tokens,
                expires_at=expires_at,
            ),
        )


def _available_budget_after_active_reservations(
    budget: CapacityAdmissionWindowBudget,
    *,
    active_reserved_requests: int,
    active_reserved_tokens: int,
) -> CapacityAdmissionWindowBudget:
    _require_non_negative_int(active_reserved_requests, "active_reserved_requests")
    _require_non_negative_int(active_reserved_tokens, "active_reserved_tokens")
    return CapacityAdmissionWindowBudget(
        remaining_requests=max(0, budget.remaining_requests - active_reserved_requests),
        remaining_tokens=max(0, budget.remaining_tokens - active_reserved_tokens),
        remaining_daily_requests=max(
            0,
            budget.remaining_daily_requests - active_reserved_requests,
        ),
        remaining_daily_tokens=max(
            0,
            budget.remaining_daily_tokens - active_reserved_tokens,
        ),
    )


def _budget_after_new_reservation(
    budget: CapacityAdmissionWindowBudget,
    *,
    reserved_tokens: int,
) -> CapacityAdmissionWindowBudget:
    _require_positive_int(reserved_tokens, "reserved_tokens")
    return CapacityAdmissionWindowBudget(
        remaining_requests=max(0, budget.remaining_requests - 1),
        remaining_tokens=max(0, budget.remaining_tokens - reserved_tokens),
        remaining_daily_requests=max(0, budget.remaining_daily_requests - 1),
        remaining_daily_tokens=max(0, budget.remaining_daily_tokens - reserved_tokens),
    )


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


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
