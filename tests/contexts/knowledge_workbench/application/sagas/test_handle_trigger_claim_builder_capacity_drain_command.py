from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.handle_trigger_claim_builder_capacity_drain_command import (
    HandleTriggerClaimBuilderCapacityDrainCommand,
    HandleTriggerClaimBuilderCapacityDrainCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.knowledge_workbench.application.sagas.trigger_claim_builder_capacity_drain_if_enabled import (
    TriggerClaimBuilderCapacityDrainIfEnabledCommand,
    TriggerClaimBuilderCapacityDrainIfEnabledResult,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)


@dataclass(slots=True)
class FakeTrigger:
    calls: list[TriggerClaimBuilderCapacityDrainIfEnabledCommand] = field(
        default_factory=list,
    )

    async def execute(
        self,
        command: TriggerClaimBuilderCapacityDrainIfEnabledCommand,
    ) -> TriggerClaimBuilderCapacityDrainIfEnabledResult:
        self.calls.append(command)
        return TriggerClaimBuilderCapacityDrainIfEnabledResult(
            skipped=False,
            skipped_reason=None,
            drained_count=1,
            execute_command_count=1,
            provider_call_count=0,
            work_item_ids=("work-item-1",),
            attempt_ids=("attempt-1",),
        )


@dataclass(slots=True)
class FakeCommandLog:
    completed_command_ids: list[WorkflowCommandId] = field(default_factory=list)
    pending_commands: list[WorkflowCommand] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        self.pending_commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed_command_ids.append(command_id)
        return _command(status=WorkflowCommandStatus.COMPLETED)


@dataclass(slots=True)
class FakeWorkflowUnitOfWork:
    command_log: FakeCommandLog = field(default_factory=FakeCommandLog)


@pytest.mark.asyncio
async def test_handler_invokes_trigger_and_marks_command_completed() -> None:
    trigger = FakeTrigger()
    uow = FakeWorkflowUnitOfWork()

    result = await HandleTriggerClaimBuilderCapacityDrainCommandHandler().execute(
        HandleTriggerClaimBuilderCapacityDrainCommand(workflow_command=_command()),
        trigger_claim_builder_capacity_drain_if_enabled=trigger,
        workflow_unit_of_work=uow,
    )

    assert result.drained_count == 1
    assert result.execute_command_count == 1
    assert trigger.calls[0].provider == "groq"
    assert trigger.calls[0].model_ref == "qwen/qwen3-32b"
    assert trigger.calls[0].account_ref == "account-1"
    assert uow.command_log.completed_command_ids == [_command().command_id]


@pytest.mark.asyncio
async def test_handler_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="command_type"):
        await HandleTriggerClaimBuilderCapacityDrainCommandHandler().execute(
            HandleTriggerClaimBuilderCapacityDrainCommand(
                workflow_command=_command(
                    command_type=(
                        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
                    ),
                )
            ),
            trigger_claim_builder_capacity_drain_if_enabled=FakeTrigger(),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
        )


@pytest.mark.parametrize("missing_key", ("provider", "model_ref", "account_ref"))
@pytest.mark.asyncio
async def test_handler_rejects_missing_provider_model_or_account(
    missing_key: str,
) -> None:
    payload = dict(_payload())
    payload.pop(missing_key)

    with pytest.raises(ValueError, match=missing_key):
        await HandleTriggerClaimBuilderCapacityDrainCommandHandler().execute(
            HandleTriggerClaimBuilderCapacityDrainCommand(
                workflow_command=_command(payload=payload),
            ),
            trigger_claim_builder_capacity_drain_if_enabled=FakeTrigger(),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
        )


@pytest.mark.asyncio
async def test_handler_does_not_append_prepare_claim_builder_dispatch_batch() -> None:
    uow = FakeWorkflowUnitOfWork()

    await HandleTriggerClaimBuilderCapacityDrainCommandHandler().execute(
        HandleTriggerClaimBuilderCapacityDrainCommand(workflow_command=_command()),
        trigger_claim_builder_capacity_drain_if_enabled=FakeTrigger(),
        workflow_unit_of_work=uow,
    )

    assert uow.command_log.pending_commands == []


@pytest.mark.asyncio
async def test_handler_provider_call_count_remains_zero_for_bridge_path() -> None:
    result = await HandleTriggerClaimBuilderCapacityDrainCommandHandler().execute(
        HandleTriggerClaimBuilderCapacityDrainCommand(workflow_command=_command()),
        trigger_claim_builder_capacity_drain_if_enabled=FakeTrigger(),
        workflow_unit_of_work=FakeWorkflowUnitOfWork(),
    )

    assert result.provider_call_count == 0


def _command(
    *,
    command_type: str = (
        KnowledgeExtractionCanonicalCommandType.TRIGGER_CLAIM_BUILDER_CAPACITY_DRAIN.value
    ),
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
    payload: dict[str, object] | None = None,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            "workflow-command:trigger-claim-builder-capacity-drain:workflow-1"
        ),
        command_type=command_type,
        workflow_run_id="workflow-1",
        idempotency_key=WorkflowIdempotencyKey(
            "trigger-claim-builder-capacity-drain:workflow-1"
        ),
        payload=_payload() if payload is None else payload,
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _payload() -> dict[str, object]:
    return {
        "workflow_run_id": "workflow-1",
        "provider": "groq",
        "model_ref": "qwen/qwen3-32b",
        "account_ref": "account-1",
        "worker_ref": "claim-builder-capacity-drain",
        "max_items": 1,
    }
