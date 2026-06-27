from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.capacity_admission_queue.application.run_capacity_window_drain import (
    RunCapacityWindowDrain,
    RunCapacityWindowDrainCommand,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_capacity_drain_bridge import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)


@dataclass(frozen=True, slots=True)
class RunClaimBuilderCapacityQueueOnceCommand:
    workflow_run_id: str
    provider: str
    model_ref: str
    account_ref: str
    now: datetime
    worker_ref: str = "claim-builder-capacity-drain"
    max_items: int | None = 1


@dataclass(frozen=True, slots=True)
class RunClaimBuilderCapacityQueueOnceResult:
    drained_count: int
    provider_call_count: int
    stop_reason: str
    work_item_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]
    selection_lane_key: CapacityAdmissionLaneKey
    execution_window_key: CapacityAdmissionLaneKey


@dataclass(frozen=True, slots=True)
class RunClaimBuilderCapacityQueueOnce:
    capacity_window_drain: RunCapacityWindowDrain

    async def execute(
        self,
        command: RunClaimBuilderCapacityQueueOnceCommand,
    ) -> RunClaimBuilderCapacityQueueOnceResult:
        selection_lane_key = CapacityAdmissionLaneKey(
            work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
            provider=command.provider,
            model_ref=command.model_ref,
            account_ref=None,
        )
        execution_window_key = CapacityAdmissionLaneKey(
            work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
            provider=command.provider,
            model_ref=command.model_ref,
            account_ref=command.account_ref,
        )
        result = await self.capacity_window_drain.execute(
            RunCapacityWindowDrainCommand(
                workflow_run_id=command.workflow_run_id,
                selection_lane_key=selection_lane_key,
                execution_window_key=execution_window_key,
                worker_ref=command.worker_ref,
                now=command.now,
                max_items=command.max_items,
            )
        )
        return RunClaimBuilderCapacityQueueOnceResult(
            drained_count=result.drained_count,
            provider_call_count=result.provider_call_count,
            stop_reason=result.stop_reason.value,
            work_item_ids=result.work_item_ids,
            attempt_ids=result.attempt_ids,
            selection_lane_key=selection_lane_key,
            execution_window_key=execution_window_key,
        )
