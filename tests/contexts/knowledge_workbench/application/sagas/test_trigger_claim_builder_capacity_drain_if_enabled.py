from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_capacity_drain_bridge import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.application.sagas import llm_dispatch_ownership
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.knowledge_workbench.application.sagas.run_claim_builder_capacity_queue_once import (
    RunClaimBuilderCapacityQueueOnceCommand,
    RunClaimBuilderCapacityQueueOnceResult,
)
from src.contexts.knowledge_workbench.application.sagas.trigger_claim_builder_capacity_drain_if_enabled import (
    TriggerClaimBuilderCapacityDrainIfEnabled,
    TriggerClaimBuilderCapacityDrainIfEnabledCommand,
)
from tests.contexts.knowledge_workbench.application.sagas.test_run_claim_builder_capacity_queue_once import (
    FakeSelector,
    FakeWorkflowUnitOfWork,
    _command,
    _item,
    _runner,
)


@dataclass(slots=True)
class FakeRunClaimBuilderCapacityQueueOnce:
    result: RunClaimBuilderCapacityQueueOnceResult
    calls: list[RunClaimBuilderCapacityQueueOnceCommand] = field(
        default_factory=list,
    )

    async def execute(
        self,
        command: RunClaimBuilderCapacityQueueOnceCommand,
    ) -> RunClaimBuilderCapacityQueueOnceResult:
        self.calls.append(command)
        return self.result


@pytest.mark.asyncio
async def test_disabled_bridge_returns_skipped_without_calling_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_dispatch_ownership,
        "CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED",
        False,
    )
    fake_run_once = FakeRunClaimBuilderCapacityQueueOnce(_result())

    result = await TriggerClaimBuilderCapacityDrainIfEnabled(fake_run_once).execute(
        _trigger_command()
    )

    assert result.skipped is True
    assert result.skipped_reason == "claim_builder_capacity_drain_bridge_disabled"
    assert fake_run_once.calls == []


@pytest.mark.asyncio
async def test_enabled_bridge_calls_run_claim_builder_capacity_queue_once() -> None:
    fake_run_once = FakeRunClaimBuilderCapacityQueueOnce(_result())

    result = await TriggerClaimBuilderCapacityDrainIfEnabled(fake_run_once).execute(
        _trigger_command()
    )

    assert result.skipped is False
    assert len(fake_run_once.calls) == 1
    assert fake_run_once.calls[0].workflow_run_id == "workflow-1"
    assert fake_run_once.calls[0].account_ref == "account-1"
    assert result.drained_count == 1


@pytest.mark.asyncio
async def test_trigger_creates_execute_claim_builder_section_through_run_once_path() -> (
    None
):
    uow = FakeWorkflowUnitOfWork()
    run_once = _runner(uow, FakeSelector(_item("work-item-1")))

    result = await TriggerClaimBuilderCapacityDrainIfEnabled(run_once).execute(
        _trigger_command()
    )

    assert result.execute_command_count == 1
    assert uow.command_log.pending_commands[0].command_type == (
        KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )


@pytest.mark.asyncio
async def test_trigger_does_not_create_prepare_claim_builder_dispatch_batch() -> None:
    uow = FakeWorkflowUnitOfWork()
    run_once = _runner(uow, FakeSelector(_item("work-item-1")))

    await TriggerClaimBuilderCapacityDrainIfEnabled(run_once).execute(
        _trigger_command()
    )

    command_types = {
        command.command_type for command in uow.command_log.pending_commands
    }
    assert (
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        not in command_types
    )


@pytest.mark.asyncio
async def test_trigger_provider_call_count_remains_zero_for_bridge_only_path() -> None:
    uow = FakeWorkflowUnitOfWork()
    run_once = _runner(uow, FakeSelector(_item("work-item-1")))

    result = await TriggerClaimBuilderCapacityDrainIfEnabled(run_once).execute(
        _trigger_command()
    )

    assert result.provider_call_count == 0


def _trigger_command() -> TriggerClaimBuilderCapacityDrainIfEnabledCommand:
    base = _command()
    return TriggerClaimBuilderCapacityDrainIfEnabledCommand(
        workflow_run_id=base.workflow_run_id,
        provider=base.provider,
        model_ref=base.model_ref,
        account_ref=base.account_ref,
        now=base.now,
    )


def _result() -> RunClaimBuilderCapacityQueueOnceResult:
    return RunClaimBuilderCapacityQueueOnceResult(
        drained_count=1,
        provider_call_count=0,
        stop_reason="DRAINED_ITEMS",
        work_item_ids=("work-item-1",),
        attempt_ids=("attempt-1",),
        selection_lane_key=CapacityAdmissionLaneKey(
            work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
            provider="groq",
            model_ref="qwen/qwen3-32b",
            account_ref=None,
        ),
        execution_window_key=CapacityAdmissionLaneKey(
            work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
            provider="groq",
            model_ref="qwen/qwen3-32b",
            account_ref="account-1",
        ),
    )
