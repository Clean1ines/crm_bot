from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
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
from src.interfaces.composition.capacity_window_admission_reservation import (
    ReserveLlmRouteCapacityForAdmission,
)


def _now() -> datetime:
    return datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


@dataclass(slots=True)
class FakeReservationRepository:
    active: tuple[LlmRouteCapacityReservationTotal, ...] = ()
    locked_routes: list[tuple[str, str, str]] = field(default_factory=list)
    reservations: list[LlmRouteCapacityReservation] = field(default_factory=list)

    async def lock_route(
        self,
        *,
        provider: str,
        account_ref: str,
        model_ref: str,
    ) -> None:
        self.locked_routes.append((provider, account_ref, model_ref))

    async def active_totals(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
        now: datetime,
    ) -> tuple[LlmRouteCapacityReservationTotal, ...]:
        return self.active

    async def reserve(self, reservation: LlmRouteCapacityReservation) -> None:
        self.reservations.append(reservation)


@dataclass(slots=True)
class FakeCapacityObservationRepository:
    observations: tuple[LlmAttemptCapacityObservation, ...] = ()

    async def latest_observations_for_accounts(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
    ) -> tuple[LlmAttemptCapacityObservation, ...]:
        return tuple(
            observation
            for observation in self.observations
            if observation.provider == provider
            and observation.account_ref in account_refs
            and observation.model_ref == model_ref
        )


def _observation(
    *,
    remaining_minute_tokens: int | None,
    minute_reset_at: datetime | None,
    remaining_daily_tokens: int | None = None,
) -> LlmAttemptCapacityObservation:
    return LlmAttemptCapacityObservation(
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
        remaining_minute_requests=None,
        remaining_minute_tokens=remaining_minute_tokens,
        remaining_daily_requests=None,
        remaining_daily_tokens=remaining_daily_tokens,
        minute_reset_at=minute_reset_at,
        daily_reset_at=None,
        actual_prompt_tokens=None,
        actual_completion_tokens=None,
        actual_total_tokens=None,
        outcome_class="rate_limit_observed",
        observed_at=_now(),
    )


def _budget() -> CapacityAdmissionWindowBudget:
    return CapacityAdmissionWindowBudget(
        remaining_requests=5,
        remaining_tokens=10_000,
        remaining_daily_requests=50,
        remaining_daily_tokens=100_000,
    )


def _lane(*, account_ref: str | None = "groq-account-1") -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        provider="groq",
        account_ref=account_ref,
        model_ref="qwen/qwen3-32b",
    )


def _item(
    *, account_ref: str | None = "groq-account-1"
) -> CapacityAdmissionSelectableWorkItem:
    return CapacityAdmissionSelectableWorkItem(
        work_item_id="work-item-1",
        lane_key=CapacityAdmissionLaneKey(
            work_kind="knowledge_workbench.claim_builder.section_extraction",
            provider="groq",
            account_ref=account_ref,
            model_ref="qwen/qwen3-32b",
        ),
        status="ready",
        required_window_tokens=3_000,
        input_tokens=2_500,
        artifact_tokens=300,
    )


@pytest.mark.asyncio
async def test_reserves_route_capacity_after_lock_and_active_totals() -> None:
    repository = FakeReservationRepository()
    reservation = ReserveLlmRouteCapacityForAdmission(repository)

    result = await reservation.reserve_capacity_for_selected_work_item(
        reservation_ref="work-item-1:attempt:1",
        attempt_id="attempt-1",
        execution_lane_key=_lane(),
        selected_work_item=_item(),
        budget=_budget(),
        now=_now(),
        expires_at=_now() + timedelta(minutes=2),
    )

    assert result.reserved is True
    assert result.reservation_summary is not None
    assert result.reservation_summary.reservation_ref == "work-item-1:attempt:1"
    assert result.reservation_summary.reserved_tokens == 3_000
    assert result.budget_after.remaining_requests == 4
    assert result.budget_after.remaining_tokens == 7_000
    assert repository.locked_routes == [("groq", "groq-account-1", "qwen/qwen3-32b")]
    assert repository.reservations[0].attempt_id == "attempt-1"


@pytest.mark.asyncio
async def test_active_reservations_reduce_available_budget_before_new_reservation() -> (
    None
):
    repository = FakeReservationRepository(
        active=(
            LlmRouteCapacityReservationTotal(
                provider="groq",
                account_ref="groq-account-1",
                model_ref="qwen/qwen3-32b",
                reserved_requests=4,
                reserved_tokens=8_000,
            ),
        )
    )
    reservation = ReserveLlmRouteCapacityForAdmission(repository)

    result = await reservation.reserve_capacity_for_selected_work_item(
        reservation_ref="work-item-1:attempt:1",
        attempt_id="attempt-1",
        execution_lane_key=_lane(),
        selected_work_item=_item(),
        budget=_budget(),
        now=_now(),
        expires_at=_now() + timedelta(minutes=2),
    )

    assert result.reserved is False
    assert (
        result.skipped_reason is CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED
    )
    assert repository.reservations == []


@pytest.mark.asyncio
async def test_missing_account_ref_is_rejected_as_route_configuration_error() -> None:
    reservation = ReserveLlmRouteCapacityForAdmission(FakeReservationRepository())

    with pytest.raises(ValueError, match="account_ref"):
        await reservation.reserve_capacity_for_selected_work_item(
            reservation_ref="work-item-1:attempt:1",
            attempt_id="attempt-1",
            execution_lane_key=_lane(account_ref=None),
            selected_work_item=_item(account_ref=None),
            budget=_budget(),
            now=_now(),
            expires_at=_now() + timedelta(minutes=2),
        )


@pytest.mark.asyncio
async def test_latest_observation_clamps_stale_payload_budget_before_reservation() -> (
    None
):
    repository = FakeReservationRepository()
    observation_repository = FakeCapacityObservationRepository(
        observations=(
            _observation(
                remaining_minute_tokens=2_500,
                minute_reset_at=_now() + timedelta(seconds=30),
            ),
        )
    )
    reservation = ReserveLlmRouteCapacityForAdmission(
        repository,
        capacity_observation_repository=observation_repository,
    )

    result = await reservation.reserve_capacity_for_selected_work_item(
        reservation_ref="work-item-1:attempt:1",
        attempt_id="attempt-1",
        execution_lane_key=_lane(),
        selected_work_item=_item(),
        budget=_budget(),
        now=_now(),
        expires_at=_now() + timedelta(minutes=2),
    )

    assert result.reserved is False
    assert (
        result.skipped_reason is CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED
    )
    assert repository.reservations == []


@pytest.mark.asyncio
async def test_expired_observation_reset_does_not_keep_window_clamped() -> None:
    repository = FakeReservationRepository()
    observation_repository = FakeCapacityObservationRepository(
        observations=(
            _observation(
                remaining_minute_tokens=2_500,
                minute_reset_at=_now() - timedelta(seconds=1),
            ),
        )
    )
    reservation = ReserveLlmRouteCapacityForAdmission(
        repository,
        capacity_observation_repository=observation_repository,
    )

    result = await reservation.reserve_capacity_for_selected_work_item(
        reservation_ref="work-item-1:attempt:1",
        attempt_id="attempt-1",
        execution_lane_key=_lane(),
        selected_work_item=_item(),
        budget=_budget(),
        now=_now(),
        expires_at=_now() + timedelta(minutes=2),
    )

    assert result.reserved is True
    assert repository.reservations[0].reserved_tokens == 3_000


@pytest.mark.asyncio
async def test_unknown_daily_observation_does_not_clamp_payload_daily_budget_to_zero() -> (
    None
):
    repository = FakeReservationRepository()
    observation_repository = FakeCapacityObservationRepository(
        observations=(
            _observation(
                remaining_minute_tokens=10_000,
                minute_reset_at=_now() + timedelta(seconds=30),
                remaining_daily_tokens=None,
            ),
        )
    )
    reservation = ReserveLlmRouteCapacityForAdmission(
        repository,
        capacity_observation_repository=observation_repository,
    )

    result = await reservation.reserve_capacity_for_selected_work_item(
        reservation_ref="work-item-1:attempt:1",
        attempt_id="attempt-1",
        execution_lane_key=_lane(),
        selected_work_item=_item(),
        budget=_budget(),
        now=_now(),
        expires_at=_now() + timedelta(minutes=2),
    )

    assert result.reserved is True


@pytest.mark.asyncio
async def test_expired_minute_reset_restores_budget_over_stale_wakeup_payload() -> None:
    repository = FakeReservationRepository()
    observation_repository = FakeCapacityObservationRepository(
        observations=(
            _observation(
                remaining_minute_tokens=2_500,
                minute_reset_at=_now() - timedelta(seconds=1),
                remaining_daily_tokens=None,
            ),
        )
    )
    reservation = ReserveLlmRouteCapacityForAdmission(
        repository,
        capacity_observation_repository=observation_repository,
    )

    stale_wakeup_budget = CapacityAdmissionWindowBudget(
        remaining_requests=0,
        remaining_tokens=2_500,
        remaining_daily_requests=0,
        remaining_daily_tokens=0,
    )

    result = await reservation.reserve_capacity_for_selected_work_item(
        reservation_ref="work-item-1:attempt:1",
        attempt_id="attempt-1",
        execution_lane_key=_lane(),
        selected_work_item=_item(),
        budget=stale_wakeup_budget,
        now=_now(),
        expires_at=_now() + timedelta(minutes=2),
    )

    assert result.reserved is True
    assert repository.reservations[0].reserved_tokens == 3_000
