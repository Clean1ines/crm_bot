from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_admission_queue.application.run_capacity_window_drain import (
    CapacityWindowDrainResult,
    RunCapacityWindowDrainCommand,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)


@dataclass(frozen=True, slots=True)
class RunCapacityLaneDrainForAvailableWindowsCommand:
    workflow_run_id: str | None
    work_kind: str
    provider: str
    model_ref: str
    now: datetime
    worker_ref_prefix: str
    max_windows: int | None = None
    max_items_per_window: int | None = None


@dataclass(frozen=True, slots=True)
class RunCapacityLaneDrainForAvailableWindowsResult:
    attempted_window_count: int
    drained_window_count: int
    provider_call_count: int
    drained_work_item_count: int
    stop_reasons: tuple[str, ...]


class CapacityAdmissionAvailableWindowResolverPort(Protocol):
    async def resolve_available_lane_keys(
        self,
        *,
        work_kind: str,
        provider: str,
        model_ref: str,
        now: datetime,
    ) -> tuple[CapacityAdmissionLaneKey, ...]: ...


class CapacityWindowDrainPort(Protocol):
    async def execute(
        self,
        command: RunCapacityWindowDrainCommand,
    ) -> CapacityWindowDrainResult: ...


@dataclass(frozen=True, slots=True)
class RunCapacityLaneDrainForAvailableWindows:
    available_window_resolver: CapacityAdmissionAvailableWindowResolverPort
    capacity_window_drain: CapacityWindowDrainPort

    async def execute(
        self,
        command: RunCapacityLaneDrainForAvailableWindowsCommand,
    ) -> RunCapacityLaneDrainForAvailableWindowsResult:
        lane_keys = await self.available_window_resolver.resolve_available_lane_keys(
            work_kind=command.work_kind,
            provider=command.provider,
            model_ref=command.model_ref,
            now=command.now,
        )
        if command.max_windows is not None:
            lane_keys = lane_keys[: command.max_windows]

        provider_call_count = 0
        drained_work_item_count = 0
        drained_window_count = 0
        stop_reasons: list[str] = []
        for window_index, lane_key in enumerate(lane_keys):
            selection_lane_key = CapacityAdmissionLaneKey(
                work_kind=lane_key.work_kind,
                provider=lane_key.provider,
                model_ref=lane_key.model_ref,
                account_ref=None,
            )
            result = await self.capacity_window_drain.execute(
                RunCapacityWindowDrainCommand(
                    workflow_run_id=command.workflow_run_id,
                    selection_lane_key=selection_lane_key,
                    execution_window_key=lane_key,
                    worker_ref=f"{command.worker_ref_prefix}:{window_index}",
                    now=command.now,
                    max_items=command.max_items_per_window,
                )
            )
            provider_call_count += result.provider_call_count
            drained_work_item_count += result.drained_count
            if result.drained_count > 0:
                drained_window_count += 1
            stop_reasons.append(result.stop_reason.value)

        return RunCapacityLaneDrainForAvailableWindowsResult(
            attempted_window_count=len(lane_keys),
            drained_window_count=drained_window_count,
            provider_call_count=provider_call_count,
            drained_work_item_count=drained_work_item_count,
            stop_reasons=tuple(stop_reasons),
        )
