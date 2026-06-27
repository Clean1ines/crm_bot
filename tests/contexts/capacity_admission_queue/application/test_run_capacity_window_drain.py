from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, cast

import pytest

from src.contexts.capacity_admission_queue.application.ports.capacity_lane_claim_repository_port import (
    CapacityLaneClaim,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_window_budget_repository_port import (
    CapacityReservation,
    CapacityWindowBudgetSnapshot,
)
from src.contexts.capacity_admission_queue.application.run_capacity_window_drain import (
    CapacityDrainStrategyResult,
    CapacityWindowDrainStopReason,
    RunCapacityWindowDrain,
    RunCapacityWindowDrainCommand,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
    SelectCapacityAdmissionWorkItem,
)
from src.contexts.capacity_admission_queue.application.sync_capacity_admission_projection_lifecycle import (
    CapacityAdmissionProjectionLifecycleUpdate,
)


def _now() -> datetime:
    return datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)


def _lane(account_ref: str | None = "account-1") -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        provider="groq",
        account_ref=account_ref,
        model_ref="qwen/qwen3-32b",
    )


def _selection_lane() -> CapacityAdmissionLaneKey:
    return _lane(account_ref=None)


def _snapshot() -> CapacityWindowBudgetSnapshot:
    return CapacityWindowBudgetSnapshot(
        provider="groq",
        account_ref="account-1",
        model_ref="qwen/qwen3-32b",
        remaining_minute_requests=10,
        remaining_minute_tokens=10_000,
        remaining_daily_requests=10,
        remaining_daily_tokens=10_000,
        reserved_minute_requests=0,
        reserved_minute_tokens=0,
        reserved_daily_requests=0,
        reserved_daily_tokens=0,
        minute_reset_at=None,
        daily_reset_at=None,
        frozen_until=None,
    )


@dataclass(slots=True)
class FakeLaneClaims:
    claim: CapacityLaneClaim | None
    released: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)

    async def claim_dirty_lane(self, **_: object) -> CapacityLaneClaim | None:
        return self.claim

    async def release_lane_claim(self, *, lane_id: str, **_: object) -> None:
        self.released.append(lane_id)

    async def clear_dirty_flag(self, *, lane_id: str, **_: object) -> None:
        self.cleared.append(lane_id)


@dataclass(slots=True)
class FakeBudget:
    snapshot: CapacityWindowBudgetSnapshot = field(default_factory=_snapshot)
    reserve_allowed: bool = True
    reservations: list[CapacityReservation] = field(default_factory=list)
    released: list[CapacityReservation] = field(default_factory=list)
    seeded_windows: list[str | None] = field(default_factory=list)
    frozen_windows: list[str | None] = field(default_factory=list)

    async def get_or_seed_window(
        self,
        *,
        account_ref: str | None,
        **_: object,
    ) -> CapacityWindowBudgetSnapshot:
        self.seeded_windows.append(account_ref)
        return self.snapshot

    async def try_reserve(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        request_count: int,
        token_count: int,
        now: datetime,
    ) -> CapacityReservation | None:
        if not self.reserve_allowed:
            return None
        reservation = CapacityReservation(
            provider=provider,
            account_ref=account_ref,
            model_ref=model_ref,
            request_count=request_count,
            token_count=token_count,
            reserved_at=now,
        )
        self.reservations.append(reservation)
        return reservation

    async def release_reservation(
        self,
        *,
        reservation: CapacityReservation,
        now: datetime,
    ) -> None:
        self.released.append(reservation)

    async def apply_capacity_observation(
        self, **_: object
    ) -> CapacityWindowBudgetSnapshot:
        return self.snapshot

    async def freeze_until(self, *, account_ref: str | None, **_: object) -> None:
        self.frozen_windows.append(account_ref)


@dataclass(slots=True)
class FakeSelector:
    retryable: CapacityAdmissionSelectableWorkItem | None = None
    ready: CapacityAdmissionSelectableWorkItem | None = None
    calls: list[str] = field(default_factory=list)

    async def select_first_retryable_failed_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        **_: object,
    ):
        assert lane_key.account_ref is None
        self.calls.append("retryable_failed")
        return self.retryable

    async def select_first_ready_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        **_: object,
    ):
        assert lane_key.account_ref is None
        self.calls.append("ready")
        return self.ready


@dataclass(slots=True)
class FakeLifecycle:
    updates: list[CapacityAdmissionProjectionLifecycleUpdate] = field(
        default_factory=list
    )

    async def sync_projection_lifecycle(
        self,
        update: CapacityAdmissionProjectionLifecycleUpdate,
    ):
        self.updates.append(update)
        return None


@dataclass(slots=True)
class FakeStrategy:
    pause: bool = False
    executed: list[str] = field(default_factory=list)
    reservations: list[CapacityReservation] = field(default_factory=list)
    execution_accounts: list[str | None] = field(default_factory=list)
    provider_call_started: bool = False
    capacity_observation_recorded: bool = False

    async def should_pause(self, **_: object) -> bool:
        return self.pause

    async def execute_admitted_work_item(
        self,
        *,
        work_item_id: str,
        execution_window_key: CapacityAdmissionLaneKey,
        reservation: CapacityReservation,
        **_: object,
    ) -> CapacityDrainStrategyResult:
        self.execution_accounts.append(execution_window_key.account_ref)
        self.reservations.append(reservation)
        self.executed.append(work_item_id)
        return CapacityDrainStrategyResult(
            work_item_id=work_item_id,
            dispatch_attempt_id=f"attempt:{work_item_id}",
            provider_call_started=self.provider_call_started,
            capacity_observation_recorded=self.capacity_observation_recorded,
        )


def _claim() -> CapacityLaneClaim:
    return CapacityLaneClaim(
        lane_id="knowledge_workbench.claim_builder.section_extraction:groq:account-1:qwen/qwen3-32b",
        lane_key=_selection_lane(),
        claimed_by="worker-1",
        claimed_until=_now(),
        claim_version=1,
    )


def _item(
    work_item_id: str, status: str = "ready"
) -> CapacityAdmissionSelectableWorkItem:
    return CapacityAdmissionSelectableWorkItem(
        work_item_id=work_item_id,
        lane_key=_selection_lane(),
        status=cast(Literal["retryable_failed", "ready"], status),
        required_window_tokens=512,
    )


@pytest.mark.asyncio
async def test_drain_returns_lane_already_claimed_without_provider_call() -> None:
    strategy = FakeStrategy()

    result = await _drain(
        lane_claims=FakeLaneClaims(claim=None),
        strategy=strategy,
    ).execute(_command())

    assert result.stop_reason is CapacityWindowDrainStopReason.LANE_ALREADY_CLAIMED
    assert result.provider_call_count == 0
    assert strategy.executed == []


@pytest.mark.asyncio
async def test_drain_selects_retryable_before_ready_and_executes_after_reservation() -> (
    None
):
    budget = FakeBudget()
    lifecycle = FakeLifecycle()
    strategy = FakeStrategy()

    result = await _drain(
        budget=budget,
        selector=FakeSelector(retryable=_item("retry-1", "retryable_failed")),
        lifecycle=lifecycle,
        strategy=strategy,
    ).execute(_command(max_items=1))

    assert result.work_item_ids == ("retry-1",)
    assert result.attempt_ids == ("attempt:retry-1",)
    assert result.provider_call_count == 0
    assert budget.reservations[0].token_count == 512
    assert budget.released == budget.reservations
    assert lifecycle.updates[0].status == "leased"
    assert strategy.executed == ["retry-1"]


@pytest.mark.asyncio
async def test_drain_budget_exhausted_no_provider_call() -> None:
    strategy = FakeStrategy()

    result = await _drain(
        budget=FakeBudget(reserve_allowed=False),
        selector=FakeSelector(ready=_item("ready-1")),
        strategy=strategy,
    ).execute(_command())

    assert result.stop_reason is CapacityWindowDrainStopReason.BUDGET_EXHAUSTED
    assert result.provider_call_count == 0
    assert strategy.executed == []


@pytest.mark.asyncio
async def test_drain_pause_requested_no_new_lease() -> None:
    lifecycle = FakeLifecycle()

    result = await _drain(
        lifecycle=lifecycle,
        selector=FakeSelector(ready=_item("ready-1")),
        strategy=FakeStrategy(pause=True),
    ).execute(_command())

    assert result.stop_reason is CapacityWindowDrainStopReason.PAUSE_REQUESTED
    assert lifecycle.updates == []


@pytest.mark.asyncio
async def test_drain_clears_dirty_flag_when_no_fitting_work() -> None:
    claims = FakeLaneClaims(claim=_claim())

    result = await _drain(
        lane_claims=claims,
        selector=FakeSelector(),
    ).execute(_command())

    assert result.stop_reason is CapacityWindowDrainStopReason.NO_FITTING_WORK
    assert claims.cleared == [_claim().lane_id]
    assert claims.released == [_claim().lane_id]


def test_drain_rejects_execution_window_without_account_ref() -> None:
    with pytest.raises(ValueError, match="execution_window_key account_ref"):
        RunCapacityWindowDrainCommand(
            workflow_run_id="workflow-1",
            selection_lane_key=_selection_lane(),
            execution_window_key=_selection_lane(),
            worker_ref="worker-1",
            now=_now(),
        )


@pytest.mark.asyncio
async def test_drain_uses_selection_lane_for_selector_and_execution_window_for_budget() -> (
    None
):
    budget = FakeBudget()
    strategy = FakeStrategy()

    await _drain(
        budget=budget,
        selector=FakeSelector(ready=_item("ready-1")),
        strategy=strategy,
    ).execute(_command(max_items=1))

    assert budget.seeded_windows == ["account-1"]
    assert budget.reservations[0].account_ref == "account-1"
    assert strategy.execution_accounts == ["account-1"]


@pytest.mark.asyncio
async def test_strategy_receives_execution_window_and_matching_reservation() -> None:
    budget = FakeBudget()
    strategy = FakeStrategy()

    await _drain(
        budget=budget,
        selector=FakeSelector(ready=_item("ready-1")),
        strategy=strategy,
    ).execute(_command(max_items=1))

    assert strategy.reservations == budget.reservations
    assert strategy.reservations[0].account_ref == "account-1"


@pytest.mark.asyncio
async def test_exhausted_window_a_does_not_exhaust_window_b() -> None:
    exhausted = FakeBudget(reserve_allowed=False)
    available = FakeBudget()
    selector = FakeSelector(ready=_item("ready-1"))

    result_a = await _drain(budget=exhausted, selector=selector).execute(
        _command(max_items=1)
    )
    result_b = await _drain(
        budget=available,
        selector=FakeSelector(ready=_item("ready-2")),
    ).execute(_command(max_items=1))

    assert result_a.stop_reason is CapacityWindowDrainStopReason.BUDGET_EXHAUSTED
    assert result_b.work_item_ids == ("ready-2",)


@pytest.mark.asyncio
async def test_two_windows_have_independent_reservations() -> None:
    first_budget = FakeBudget()
    second_budget = FakeBudget()

    await _drain(
        budget=first_budget,
        selector=FakeSelector(ready=_item("ready-1")),
    ).execute(_command(max_items=1))
    await _drain(
        budget=second_budget,
        selector=FakeSelector(ready=_item("ready-2")),
    ).execute(
        RunCapacityWindowDrainCommand(
            workflow_run_id="workflow-1",
            selection_lane_key=_selection_lane(),
            execution_window_key=_lane("account-2"),
            worker_ref="worker-2",
            now=_now(),
            max_items=1,
        )
    )

    assert first_budget.reservations[0].account_ref == "account-1"
    assert second_budget.reservations[0].account_ref == "account-2"


def _command(max_items: int | None = None) -> RunCapacityWindowDrainCommand:
    return RunCapacityWindowDrainCommand(
        workflow_run_id="workflow-1",
        selection_lane_key=_selection_lane(),
        execution_window_key=_lane(),
        worker_ref="worker-1",
        now=_now(),
        max_items=max_items,
    )


def _drain(
    *,
    lane_claims: FakeLaneClaims | None = None,
    budget: FakeBudget | None = None,
    selector: FakeSelector | None = None,
    lifecycle: FakeLifecycle | None = None,
    strategy: FakeStrategy | None = None,
) -> RunCapacityWindowDrain:
    return RunCapacityWindowDrain(
        lane_claim_repository=lane_claims or FakeLaneClaims(claim=_claim()),
        budget_repository=budget or FakeBudget(),
        capacity_selector=SelectCapacityAdmissionWorkItem(selector or FakeSelector()),
        projection_lifecycle_synchronizer=lifecycle or FakeLifecycle(),
        strategy=strategy or FakeStrategy(),
    )
