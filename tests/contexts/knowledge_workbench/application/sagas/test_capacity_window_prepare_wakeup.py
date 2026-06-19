from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.knowledge_workbench.application.sagas.append_capacity_window_prepare_wakeup import (
    append_capacity_window_prepare_wakeup,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    _prepare_llm_dispatch_batch_command,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
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


class FakeCommandLog:
    def __init__(self) -> None:
        self.pending_commands: list[WorkflowCommand] = []

    async def append_pending_command(self, command: WorkflowCommand) -> None:
        self.pending_commands.append(command)


class FakeWorkflowUnitOfWork:
    def __init__(self) -> None:
        self.command_log = FakeCommandLog()


def _now() -> datetime:
    return datetime(2026, 6, 19, 13, 0, 5, tzinfo=timezone.utc)


def _source_command(
    *,
    command_type: KnowledgeExtractionCanonicalCommandType,
    payload: dict[str, object],
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:source-command"),
        command_type=command_type.value,
        workflow_run_id="workflow-1",
        idempotency_key=WorkflowIdempotencyKey("source-command"),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _observation(
    *, account_ref: str, reset_after_seconds: int
) -> LlmAttemptCapacityObservation:
    return LlmAttemptCapacityObservation(
        provider="groq",
        account_ref=account_ref,
        model_ref="qwen/qwen3-32b",
        remaining_minute_requests=1,
        remaining_minute_tokens=6000,
        remaining_daily_requests=100,
        remaining_daily_tokens=500000,
        minute_reset_at=_now() + timedelta(seconds=reset_after_seconds),
        daily_reset_at=None,
        actual_prompt_tokens=3000,
        actual_completion_tokens=100,
        actual_total_tokens=3100,
        outcome_class="succeeded",
        observed_at=_now(),
    )


@pytest.mark.asyncio
async def test_capacity_observation_appends_single_account_prepare_wakeup() -> None:
    fake_unit_of_work = FakeWorkflowUnitOfWork()
    source_command = _source_command(
        command_type=KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION,
        payload={
            "workflow_run_id": "workflow-1",
            "source_document_ref": "doc-1",
            "scheduled_work_item_count": 12,
            "active_model_ref": "qwen/qwen3-32b",
            "llm_dispatch_preparation": {
                "active_model_ref": "qwen/qwen3-32b",
                "profile": {
                    "profile_id": "claim-builder",
                    "estimated_prompt_tokens": 1000,
                    "estimated_completion_tokens": 2000,
                    "estimated_requests": 1,
                },
                "account_capacities": [
                    {
                        "provider": "groq",
                        "account_ref": "groq_org_1",
                        "model_ref": "qwen/qwen3-32b",
                        "remaining_minute_requests": 1,
                        "remaining_minute_tokens": 6000,
                        "remaining_daily_requests": 100,
                        "remaining_daily_tokens": 500000,
                    },
                    {
                        "provider": "groq",
                        "account_ref": "groq_org_2",
                        "model_ref": "qwen/qwen3-32b",
                        "remaining_minute_requests": 1,
                        "remaining_minute_tokens": 6000,
                        "remaining_daily_requests": 100,
                        "remaining_daily_tokens": 500000,
                    },
                ],
            },
        },
    )

    wakeup = await append_capacity_window_prepare_wakeup(
        workflow_unit_of_work=cast(WorkflowRuntimeUnitOfWorkPort, fake_unit_of_work),
        source_command=source_command,
        workflow_run_id="workflow-1",
        prepare_command_type=KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH,
        capacity_observation=_observation(
            account_ref="groq_org_2", reset_after_seconds=60
        ),
        occurred_at=_now(),
    )

    assert wakeup is not None
    assert len(fake_unit_of_work.command_log.pending_commands) == 1
    command = fake_unit_of_work.command_log.pending_commands[0]
    assert command.command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    )
    assert command.run_after == _now() + timedelta(seconds=60)
    assert command.payload["capacity_window_provider_account_refs"] == ["groq_org_2"]
    assert command.payload["capacity_window_model_ref"] == "qwen/qwen3-32b"
    dispatch_preparation = command.payload["llm_dispatch_preparation"]
    assert isinstance(dispatch_preparation, dict)
    assert "account_capacities" not in dispatch_preparation


def test_claim_builder_prepare_command_uses_single_capacity_window_account() -> None:
    workflow_command = _source_command(
        command_type=KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH,
        payload={
            "workflow_run_id": "workflow-1",
            "source_document_ref": "doc-1",
            "scheduled_work_item_count": 12,
            "capacity_window_provider_account_refs": ["groq_org_2"],
            "active_model_ref": "qwen/qwen3-32b",
            "llm_dispatch_preparation": {
                "active_model_ref": "qwen/qwen3-32b",
                "profile": {
                    "profile_id": "claim-builder",
                    "estimated_prompt_tokens": 1000,
                    "estimated_completion_tokens": 2000,
                    "estimated_requests": 1,
                },
            },
        },
    )

    command = _prepare_llm_dispatch_batch_command(
        workflow_command=workflow_command,
        workflow_run_id="workflow-1",
        occurred_at=_now(),
    )

    assert command.provider_account_refs == ("groq_org_2",)
    assert command.requested_items == 12
    assert command.active_model_ref == "qwen/qwen3-32b"
