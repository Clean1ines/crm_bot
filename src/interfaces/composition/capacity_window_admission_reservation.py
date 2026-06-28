from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_admission_queue.application.capacity_window_admission_pass import (
    CapacityWindowAdmissionCapacityPreviewResult,
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
from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
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


class LlmAttemptCapacityObservationReadRepositoryPort(Protocol):
    async def latest_observations_for_accounts(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
    ) -> tuple[LlmAttemptCapacityObservation, ...]: ...


@dataclass(frozen=True, slots=True)
class ReserveLlmRouteCapacityForAdmission:
    reservation_repository: LlmRouteCapacityReservationRepositoryPort
    capacity_observation_repository: (
        LlmAttemptCapacityObservationReadRepositoryPort | None
    ) = None

    async def preview_capacity_for_selected_work_item(
        self,
        *,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        execution_lane_key: CapacityAdmissionLaneKey,
        budget: CapacityAdmissionWindowBudget,
        now: datetime,
    ) -> CapacityWindowAdmissionCapacityPreviewResult:
        _require_timezone_aware(now, "now")

        lane_key = execution_lane_key
        if lane_key.account_ref is None:
            raise ValueError("capacity admission preview requires account_ref")
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
        live_budget = await _budget_after_latest_capacity_observation(
            budget,
            observation_repository=self.capacity_observation_repository,
            provider=lane_key.provider,
            account_ref=lane_key.account_ref,
            model_ref=lane_key.model_ref,
            now=now,
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
            live_budget,
            active_reserved_requests=active_reserved_requests,
            active_reserved_tokens=active_reserved_tokens,
        )
        if not available_budget.admits_any_work:
            return CapacityWindowAdmissionCapacityPreviewResult(
                capacity_available=False,
                budget_after_active_reservations=available_budget,
                skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            )

        if (
            selected_work_item.required_window_tokens
            > available_budget.max_required_window_tokens
        ):
            return CapacityWindowAdmissionCapacityPreviewResult(
                capacity_available=False,
                budget_after_active_reservations=available_budget,
                skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            )

        return CapacityWindowAdmissionCapacityPreviewResult(
            capacity_available=True,
            budget_after_active_reservations=available_budget,
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
        live_budget = await _budget_after_latest_capacity_observation(
            budget,
            observation_repository=self.capacity_observation_repository,
            provider=lane_key.provider,
            account_ref=lane_key.account_ref,
            model_ref=lane_key.model_ref,
            now=now,
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
            live_budget,
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


async def _budget_after_latest_capacity_observation(
    budget: CapacityAdmissionWindowBudget,
    *,
    observation_repository: LlmAttemptCapacityObservationReadRepositoryPort | None,
    provider: str,
    account_ref: str,
    model_ref: str,
    now: datetime,
) -> CapacityAdmissionWindowBudget:
    if observation_repository is None:
        return budget

    observations = await observation_repository.latest_observations_for_accounts(
        provider=provider,
        account_refs=(account_ref,),
        model_ref=model_ref,
    )
    if not observations:
        return budget

    return _budget_clamped_by_observation(
        budget,
        observation=observations[0],
        now=now,
    )


def _budget_clamped_by_observation(
    budget: CapacityAdmissionWindowBudget,
    *,
    observation: LlmAttemptCapacityObservation,
    now: datetime,
) -> CapacityAdmissionWindowBudget:
    _require_timezone_aware(now, "now")

    minute_window_has_reset = (
        observation.minute_reset_at is not None and now >= observation.minute_reset_at
    )
    daily_window_has_reset = (
        observation.daily_reset_at is not None and now >= observation.daily_reset_at
    )

    if minute_window_has_reset:
        remaining_requests = max(budget.remaining_requests, 1)
        remaining_tokens = max(
            budget.remaining_tokens,
            _restored_minute_token_limit_for_model(
                observation.model_ref,
                fallback=budget.remaining_tokens,
            ),
        )
    else:
        remaining_requests = _min_if_observed(
            budget.remaining_requests,
            observation.remaining_minute_requests,
        )
        remaining_tokens = _min_if_observed(
            budget.remaining_tokens,
            observation.remaining_minute_tokens,
        )

    daily_observation_unknown = (
        observation.remaining_daily_requests is None
        and observation.remaining_daily_tokens is None
        and observation.daily_reset_at is None
    )

    if daily_window_has_reset or daily_observation_unknown:
        remaining_daily_requests = max(
            budget.remaining_daily_requests,
            remaining_requests,
        )
        remaining_daily_tokens = max(
            budget.remaining_daily_tokens,
            remaining_tokens,
        )
    else:
        remaining_daily_requests = _min_if_observed(
            budget.remaining_daily_requests,
            observation.remaining_daily_requests,
        )
        remaining_daily_tokens = _min_if_observed(
            budget.remaining_daily_tokens,
            observation.remaining_daily_tokens,
        )

    return CapacityAdmissionWindowBudget(
        remaining_requests=remaining_requests,
        remaining_tokens=remaining_tokens,
        remaining_daily_requests=remaining_daily_requests,
        remaining_daily_tokens=remaining_daily_tokens,
    )


def _restored_minute_token_limit_for_model(model_ref: str, *, fallback: int) -> int:
    _require_non_empty_text(model_ref, "model_ref")
    _require_non_negative_int(fallback, "fallback")

    configured_minute_token_limits = {
        "qwen/qwen3-32b": 6_000,
    }
    return configured_minute_token_limits.get(model_ref, fallback)


def _min_if_observed(
    configured_or_payload_value: int, observed_value: int | None
) -> int:
    _require_non_negative_int(
        configured_or_payload_value,
        "configured_or_payload_value",
    )
    if observed_value is None:
        return configured_or_payload_value
    _require_non_negative_int(observed_value, "observed_value")
    return min(configured_or_payload_value, observed_value)


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
