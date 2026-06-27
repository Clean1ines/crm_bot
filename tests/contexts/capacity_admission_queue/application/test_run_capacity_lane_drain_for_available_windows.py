from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.capacity_admission_queue.application.run_capacity_lane_drain_for_available_windows import (
    RunCapacityLaneDrainForAvailableWindows,
    RunCapacityLaneDrainForAvailableWindowsCommand,
)
from src.contexts.capacity_admission_queue.application.run_capacity_window_drain import (
    CapacityWindowDrainResult,
    CapacityWindowDrainStopReason,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)


def _lane(account_ref: str) -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="kind",
        provider="groq",
        account_ref=account_ref,
        model_ref="model",
    )


@dataclass(slots=True)
class FakeResolver:
    lanes: tuple[CapacityAdmissionLaneKey, ...]

    async def resolve_available_lane_keys(self, **_: object):
        return self.lanes


@dataclass(slots=True)
class FakeWindowDrain:
    results: list[CapacityWindowDrainResult]
    attempted_accounts: list[str | None] = field(default_factory=list)
    selection_accounts: list[str | None] = field(default_factory=list)

    async def execute(self, command):
        self.selection_accounts.append(command.selection_lane_key.account_ref)
        self.attempted_accounts.append(command.execution_window_key.account_ref)
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_all_available_windows_are_attempted() -> None:
    window_drain = FakeWindowDrain(
        results=[
            _result("lane-1", 0, CapacityWindowDrainStopReason.LANE_ALREADY_CLAIMED),
            _result("lane-2", 1, CapacityWindowDrainStopReason.DRAINED_ITEMS),
        ]
    )

    result = await RunCapacityLaneDrainForAvailableWindows(
        available_window_resolver=FakeResolver((_lane("a"), _lane("b"))),
        capacity_window_drain=window_drain,
    ).execute(_command())

    assert window_drain.attempted_accounts == ["a", "b"]
    assert window_drain.selection_accounts == [None, None]
    assert result.attempted_window_count == 2
    assert result.drained_window_count == 1
    assert result.drained_work_item_count == 1


@pytest.mark.asyncio
async def test_no_windows_available_returns_zero_without_provider_call() -> None:
    result = await RunCapacityLaneDrainForAvailableWindows(
        available_window_resolver=FakeResolver(()),
        capacity_window_drain=FakeWindowDrain(results=[]),
    ).execute(_command())

    assert result.attempted_window_count == 0
    assert result.provider_call_count == 0
    assert result.stop_reasons == ()


def _command() -> RunCapacityLaneDrainForAvailableWindowsCommand:
    return RunCapacityLaneDrainForAvailableWindowsCommand(
        workflow_run_id="workflow-1",
        work_kind="kind",
        provider="groq",
        model_ref="model",
        now=_now(),
        worker_ref_prefix="worker",
    )


def _result(
    lane_id: str,
    drained_count: int,
    stop_reason: CapacityWindowDrainStopReason,
) -> CapacityWindowDrainResult:
    return CapacityWindowDrainResult(
        lane_id=lane_id,
        drained_count=drained_count,
        provider_call_count=drained_count,
        stop_reason=stop_reason,
        work_item_ids=tuple(f"work-{index}" for index in range(drained_count)),
        attempt_ids=tuple(f"attempt-{index}" for index in range(drained_count)),
    )
