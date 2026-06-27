from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from src.contexts.capacity_admission_queue.application.ports.capacity_lane_claim_repository_port import (
    CapacityLaneClaimRepositoryPort,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_window_budget_repository_port import (
    CapacityReservation,
    CapacityWindowBudgetRepositoryPort,
    CapacityWindowBudgetSnapshot,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionWindowBudget,
    SelectCapacityAdmissionWorkItem,
    SelectCapacityAdmissionWorkItemCommand,
)
from src.contexts.capacity_admission_queue.application.sync_capacity_admission_projection_lifecycle import (
    CapacityAdmissionProjectionLifecycleSynchronizerPort,
    CapacityAdmissionProjectionLifecycleUpdate,
)


class CapacityWindowDrainStopReason(StrEnum):
    DRAINED_ITEMS = "DRAINED_ITEMS"
    NO_FITTING_WORK = "NO_FITTING_WORK"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    WINDOW_FROZEN = "WINDOW_FROZEN"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    LANE_ALREADY_CLAIMED = "LANE_ALREADY_CLAIMED"
    MAX_ITEMS_REACHED = "MAX_ITEMS_REACHED"


@dataclass(frozen=True, slots=True)
class RunCapacityWindowDrainCommand:
    workflow_run_id: str | None
    selection_lane_key: CapacityAdmissionLaneKey
    execution_window_key: CapacityAdmissionLaneKey
    worker_ref: str
    now: datetime
    remaining_minute_requests: int
    remaining_minute_tokens: int
    remaining_daily_requests: int
    remaining_daily_tokens: int
    max_items: int | None = None
    claim_ttl_seconds: int = 90

    def __post_init__(self) -> None:
        if self.execution_window_key.account_ref is None:
            raise ValueError("execution_window_key account_ref is required")
        for field_name, value in (
            ("remaining_minute_requests", self.remaining_minute_requests),
            ("remaining_minute_tokens", self.remaining_minute_tokens),
            ("remaining_daily_requests", self.remaining_daily_requests),
            ("remaining_daily_tokens", self.remaining_daily_tokens),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative int")
        if self.selection_lane_key.work_kind != self.execution_window_key.work_kind:
            raise ValueError("selection and execution work_kind must match")
        if self.selection_lane_key.provider != self.execution_window_key.provider:
            raise ValueError("selection and execution provider must match")
        if self.selection_lane_key.model_ref != self.execution_window_key.model_ref:
            raise ValueError("selection and execution model_ref must match")


@dataclass(frozen=True, slots=True)
class CapacityWindowDrainResult:
    lane_id: str
    drained_count: int
    provider_call_count: int
    stop_reason: CapacityWindowDrainStopReason
    work_item_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapacityDrainStrategyResult:
    work_item_id: str
    dispatch_attempt_id: str | None
    provider_call_started: bool
    capacity_observation_recorded: bool
    freeze_until: datetime | None = None

    def __post_init__(self) -> None:
        if not self.work_item_id:
            raise ValueError("work_item_id must be non-empty")
        if self.dispatch_attempt_id is not None and not self.dispatch_attempt_id:
            raise ValueError("dispatch_attempt_id must be non-empty")
        if self.capacity_observation_recorded and not self.provider_call_started:
            raise ValueError(
                "capacity_observation_recorded requires provider_call_started"
            )
        if (
            self.provider_call_started
            and not self.capacity_observation_recorded
            and self.freeze_until is None
        ):
            raise ValueError(
                "freeze_until is required when provider started without observation"
            )


class CapacityWindowDrainStrategy(Protocol):
    async def execute_admitted_work_item(
        self,
        *,
        work_item_id: str,
        selection_lane_key: CapacityAdmissionLaneKey,
        execution_window_key: CapacityAdmissionLaneKey,
        reservation: CapacityReservation,
        worker_ref: str,
        now: datetime,
    ) -> CapacityDrainStrategyResult: ...

    async def should_pause(
        self,
        *,
        workflow_run_id: str | None,
        now: datetime,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class RunCapacityWindowDrain:
    lane_claim_repository: CapacityLaneClaimRepositoryPort
    budget_repository: CapacityWindowBudgetRepositoryPort
    capacity_selector: SelectCapacityAdmissionWorkItem
    projection_lifecycle_synchronizer: (
        CapacityAdmissionProjectionLifecycleSynchronizerPort
    )
    strategy: CapacityWindowDrainStrategy

    async def execute(
        self,
        command: RunCapacityWindowDrainCommand,
    ) -> CapacityWindowDrainResult:
        claim = await self.lane_claim_repository.claim_dirty_lane(
            lane_key=command.selection_lane_key,
            worker_ref=command.worker_ref,
            now=command.now,
            claim_ttl_seconds=command.claim_ttl_seconds,
        )
        lane_id = _lane_id(command.selection_lane_key)
        if claim is None:
            return _result(
                lane_id=lane_id,
                stop_reason=CapacityWindowDrainStopReason.LANE_ALREADY_CLAIMED,
            )

        drained_work_item_ids: list[str] = []
        attempt_ids: list[str] = []
        provider_call_count = 0
        stop_reason = CapacityWindowDrainStopReason.NO_FITTING_WORK
        should_clear_dirty_flag = False
        try:
            while (
                command.max_items is None
                or len(drained_work_item_ids) < command.max_items
            ):
                if await self.strategy.should_pause(
                    workflow_run_id=command.workflow_run_id,
                    now=command.now,
                ):
                    stop_reason = CapacityWindowDrainStopReason.PAUSE_REQUESTED
                    break

                snapshot = await self.budget_repository.apply_capacity_observation(
                    provider=command.execution_window_key.provider,
                    account_ref=command.execution_window_key.account_ref,
                    model_ref=command.execution_window_key.model_ref,
                    remaining_minute_requests=command.remaining_minute_requests,
                    remaining_minute_tokens=command.remaining_minute_tokens,
                    remaining_daily_requests=command.remaining_daily_requests,
                    remaining_daily_tokens=command.remaining_daily_tokens,
                    minute_reset_at=None,
                    daily_reset_at=None,
                    observed_at=command.now,
                )
                if (
                    snapshot.frozen_until is not None
                    and snapshot.frozen_until > command.now
                ):
                    stop_reason = CapacityWindowDrainStopReason.WINDOW_FROZEN
                    break

                budget = _budget_from_snapshot(snapshot)
                selection = await self.capacity_selector.execute(
                    SelectCapacityAdmissionWorkItemCommand(
                        lane_key=command.selection_lane_key,
                        budget=budget,
                    )
                )
                selected_work_item = selection.selected_work_item
                if selected_work_item is None:
                    stop_reason = CapacityWindowDrainStopReason.NO_FITTING_WORK
                    should_clear_dirty_flag = True
                    break

                reservation = await self.budget_repository.try_reserve(
                    provider=command.execution_window_key.provider,
                    account_ref=command.execution_window_key.account_ref,
                    model_ref=command.execution_window_key.model_ref,
                    request_count=1,
                    token_count=selected_work_item.required_window_tokens,
                    now=command.now,
                )
                if reservation is None:
                    stop_reason = CapacityWindowDrainStopReason.BUDGET_EXHAUSTED
                    break

                await self.projection_lifecycle_synchronizer.sync_projection_lifecycle(
                    CapacityAdmissionProjectionLifecycleUpdate(
                        work_item_id=selected_work_item.work_item_id,
                        status="leased",
                        changed_at=command.now,
                    )
                )
                try:
                    strategy_result = await self.strategy.execute_admitted_work_item(
                        work_item_id=selected_work_item.work_item_id,
                        selection_lane_key=command.selection_lane_key,
                        execution_window_key=command.execution_window_key,
                        reservation=reservation,
                        worker_ref=command.worker_ref,
                        now=command.now,
                    )
                except Exception:
                    await self.budget_repository.release_reservation(
                        reservation=reservation,
                        now=command.now,
                    )
                    raise

                if not strategy_result.provider_call_started:
                    await self.budget_repository.release_reservation(
                        reservation=reservation,
                        now=command.now,
                    )
                elif strategy_result.capacity_observation_recorded:
                    await self.budget_repository.release_reservation(
                        reservation=reservation,
                        now=command.now,
                    )
                elif strategy_result.freeze_until is not None:
                    await self.budget_repository.freeze_until(
                        provider=command.execution_window_key.provider,
                        account_ref=command.execution_window_key.account_ref,
                        model_ref=command.execution_window_key.model_ref,
                        frozen_until=strategy_result.freeze_until,
                        now=command.now,
                    )

                if strategy_result.provider_call_started:
                    provider_call_count += 1
                drained_work_item_ids.append(selected_work_item.work_item_id)
                if strategy_result.dispatch_attempt_id is not None:
                    attempt_ids.append(strategy_result.dispatch_attempt_id)

            else:
                stop_reason = CapacityWindowDrainStopReason.MAX_ITEMS_REACHED

            if (
                drained_work_item_ids
                and stop_reason is CapacityWindowDrainStopReason.NO_FITTING_WORK
            ):
                stop_reason = CapacityWindowDrainStopReason.DRAINED_ITEMS

            if should_clear_dirty_flag:
                await self.lane_claim_repository.clear_dirty_flag(
                    lane_id=claim.lane_id,
                    worker_ref=command.worker_ref,
                    now=command.now,
                )
        finally:
            await self.lane_claim_repository.release_lane_claim(
                lane_id=claim.lane_id,
                worker_ref=command.worker_ref,
                now=command.now,
            )

        return _result(
            lane_id=claim.lane_id,
            drained_count=len(drained_work_item_ids),
            provider_call_count=provider_call_count,
            stop_reason=stop_reason,
            work_item_ids=tuple(drained_work_item_ids),
            attempt_ids=tuple(attempt_ids),
        )


def _budget_from_snapshot(
    snapshot: CapacityWindowBudgetSnapshot,
) -> CapacityAdmissionWindowBudget:
    return CapacityAdmissionWindowBudget(
        remaining_requests=max(
            0,
            _remaining(snapshot.remaining_minute_requests)
            - snapshot.reserved_minute_requests,
        ),
        remaining_tokens=max(
            0,
            _remaining(snapshot.remaining_minute_tokens)
            - snapshot.reserved_minute_tokens,
        ),
        remaining_daily_requests=max(
            0,
            _remaining(snapshot.remaining_daily_requests)
            - snapshot.reserved_daily_requests,
        ),
        remaining_daily_tokens=max(
            0,
            _remaining(snapshot.remaining_daily_tokens)
            - snapshot.reserved_daily_tokens,
        ),
    )


def _remaining(value: int | None) -> int:
    if value is None:
        return 1
    return value


def _lane_id(lane_key: CapacityAdmissionLaneKey) -> str:
    account_ref = lane_key.account_ref if lane_key.account_ref is not None else "-"
    return (
        f"{lane_key.work_kind}:{lane_key.provider}:{account_ref}:{lane_key.model_ref}"
    )


def _result(
    *,
    lane_id: str,
    stop_reason: CapacityWindowDrainStopReason,
    drained_count: int = 0,
    provider_call_count: int = 0,
    work_item_ids: tuple[str, ...] = (),
    attempt_ids: tuple[str, ...] = (),
) -> CapacityWindowDrainResult:
    return CapacityWindowDrainResult(
        lane_id=lane_id,
        drained_count=drained_count,
        provider_call_count=provider_call_count,
        stop_reason=stop_reason,
        work_item_ids=work_item_ids,
        attempt_ids=attempt_ids,
    )
