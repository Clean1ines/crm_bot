from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.application.sagas import llm_dispatch_ownership
from src.contexts.knowledge_workbench.application.sagas.run_claim_builder_capacity_queue_once import (
    RunClaimBuilderCapacityQueueOnceCommand,
    RunClaimBuilderCapacityQueueOnceResult,
)


class RunClaimBuilderCapacityQueueOncePort(Protocol):
    async def execute(
        self,
        command: RunClaimBuilderCapacityQueueOnceCommand,
    ) -> RunClaimBuilderCapacityQueueOnceResult: ...


@dataclass(frozen=True, slots=True)
class TriggerClaimBuilderCapacityDrainIfEnabledCommand:
    workflow_run_id: str
    provider: str
    model_ref: str
    account_ref: str
    now: datetime
    worker_ref: str = "claim-builder-capacity-drain"
    max_items: int | None = 1


@dataclass(frozen=True, slots=True)
class TriggerClaimBuilderCapacityDrainIfEnabledResult:
    skipped: bool
    skipped_reason: str | None
    drained_count: int
    execute_command_count: int
    provider_call_count: int
    work_item_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TriggerClaimBuilderCapacityDrainIfEnabled:
    run_claim_builder_capacity_queue_once: RunClaimBuilderCapacityQueueOncePort

    async def execute(
        self,
        command: TriggerClaimBuilderCapacityDrainIfEnabledCommand,
    ) -> TriggerClaimBuilderCapacityDrainIfEnabledResult:
        if not llm_dispatch_ownership.CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED:
            return _skipped("claim_builder_capacity_drain_bridge_disabled")
        if not llm_dispatch_ownership.CAPACITY_QUEUE_RUNTIME_CORE_ENABLED:
            return _skipped("capacity_queue_runtime_core_disabled")

        result = await self.run_claim_builder_capacity_queue_once.execute(
            RunClaimBuilderCapacityQueueOnceCommand(
                workflow_run_id=command.workflow_run_id,
                provider=command.provider,
                model_ref=command.model_ref,
                account_ref=command.account_ref,
                now=command.now,
                worker_ref=command.worker_ref,
                max_items=command.max_items,
            )
        )
        return TriggerClaimBuilderCapacityDrainIfEnabledResult(
            skipped=False,
            skipped_reason=None,
            drained_count=result.drained_count,
            execute_command_count=result.drained_count,
            provider_call_count=result.provider_call_count,
            work_item_ids=result.work_item_ids,
            attempt_ids=result.attempt_ids,
        )


def _skipped(reason: str) -> TriggerClaimBuilderCapacityDrainIfEnabledResult:
    return TriggerClaimBuilderCapacityDrainIfEnabledResult(
        skipped=True,
        skipped_reason=reason,
        drained_count=0,
        execute_command_count=0,
        provider_call_count=0,
        work_item_ids=(),
        attempt_ids=(),
    )
