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


def _budget() -> CapacityAdmissionWindowBudget:
    return CapacityAdmissionWindowBudget(
        remaining_requests=5,
        remaining_tokens=10_000,
        remaining_daily_requests=50,
        remaining_daily_tokens=100_000,
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
        reserved_total_tokens=3_000,
        estimated_input_tokens=2_500,
        estimated_output_tokens=300,
        effective_output_cap_tokens=500,
    )


@pytest.mark.asyncio
async def test_reserves_route_capacity_after_lock_and_active_totals() -> None:
    repository = FakeReservationRepository()
    reservation = ReserveLlmRouteCapacityForAdmission(repository)

    result = await reservation.reserve_capacity_for_selected_work_item(
        reservation_ref="work-item-1:attempt:1",
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
    assert repository.reservations[0].attempt_id == "work-item-1:attempt:1"


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
            selected_work_item=_item(account_ref=None),
            budget=_budget(),
            now=_now(),
            expires_at=_now() + timedelta(minutes=2),
        )
