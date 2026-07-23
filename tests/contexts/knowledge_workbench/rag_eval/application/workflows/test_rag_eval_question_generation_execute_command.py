from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.drain_workbench_rag_eval_workflow_commands import (
    DrainWorkbenchRagEvalWorkflowCommands,
    DrainWorkbenchRagEvalWorkflowCommandsCommand,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_question_generation import (
    ExecuteWorkbenchRagEvalQuestionGenerationCommand,
    ExecuteWorkbenchRagEvalQuestionGenerationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_question_generation_command import (
    HandleExecuteWorkbenchRagEvalQuestionGenerationCommand,
    HandleExecuteWorkbenchRagEvalQuestionGenerationCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
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


NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


def _execute_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            "workflow-command:execute-rag-eval-qgen:attempt-1"
        ),
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION.value
        ),
        workflow_run_id="run-1",
        idempotency_key=WorkflowIdempotencyKey("execute-rag-eval-qgen:attempt-1"),
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": "run-1",
            "project_id": "project-1",
            "publication_id": None,
            "source_document_ref": None,
            "dispatch_attempt_id": "attempt-1",
            "work_item_id": "item-1",
            "scheduled_work_item_count": 2,
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


@dataclass(slots=True)
class FakeQuestionGenerationExecutor:
    result: ExecuteWorkbenchRagEvalQuestionGenerationResult
    commands: list[ExecuteWorkbenchRagEvalQuestionGenerationCommand] = field(
        default_factory=list
    )

    async def execute(
        self,
        command: ExecuteWorkbenchRagEvalQuestionGenerationCommand,
    ) -> ExecuteWorkbenchRagEvalQuestionGenerationResult:
        self.commands.append(command)
        return self.result


@dataclass(slots=True)
class FakeCapacityRepository:
    observations: list[LlmAttemptCapacityObservation] = field(default_factory=list)

    async def record_observation(
        self,
        observation: LlmAttemptCapacityObservation,
    ) -> None:
        self.observations.append(observation)


@dataclass(slots=True)
class FakeCommandLog:
    pending: tuple[WorkflowCommand, ...] = ()
    appended: list[WorkflowCommand] = field(default_factory=list)
    completed: list[WorkflowCommandId] = field(default_factory=list)

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        assert workflow_run_id == "run-1"
        return self.pending[:limit]

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        self.appended.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed.append(command_id)
        return _execute_command()


@dataclass(slots=True)
class FakeOutbox:
    events: list[object] = field(default_factory=list)

    async def append_event(self, event):
        self.events.append(event)
        return event


@dataclass(slots=True)
class FakeTimeline:
    entries: list[object] = field(default_factory=list)

    async def append_entry(self, entry):
        self.entries.append(entry)
        return entry


@dataclass(slots=True)
class FakeWorkflowUnitOfWork:
    command_log: FakeCommandLog
    outbox: FakeOutbox = field(default_factory=FakeOutbox)
    timeline: FakeTimeline = field(default_factory=FakeTimeline)


def _capacity_payload() -> dict[str, object]:
    return {
        "provider": "groq",
        "account_ref": "groq_org_primary",
        "model_ref": "qwen/qwen3.6-27b",
        "remaining_minute_requests": 29,
        "remaining_minute_tokens": 5000,
        "remaining_daily_requests": 999,
        "remaining_daily_tokens": 900000,
        "minute_reset_at": NOW + timedelta(minutes=1),
        "daily_reset_at": NOW + timedelta(days=1),
        "actual_prompt_tokens": 1200,
        "actual_completion_tokens": 700,
        "actual_total_tokens": 1900,
        "outcome_class": "success",
        "observed_at": NOW,
    }


@pytest.mark.asyncio
async def test_execute_handler_records_capacity_and_appends_reconcile() -> None:
    executor = FakeQuestionGenerationExecutor(
        result=ExecuteWorkbenchRagEvalQuestionGenerationResult(
            dispatch_attempt_id="attempt-1",
            work_item_id="item-1",
            saved_question_count=10,
            outcome_status="succeeded",
            finished_at=NOW,
            capacity_observation=_capacity_payload(),
            error_kind=None,
            next_attempt_at=None,
        )
    )
    capacity_repository = FakeCapacityRepository()
    unit_of_work = FakeWorkflowUnitOfWork(
        command_log=FakeCommandLog(),
    )

    result = await (
        HandleExecuteWorkbenchRagEvalQuestionGenerationCommandHandler().execute(
            HandleExecuteWorkbenchRagEvalQuestionGenerationCommand(
                workflow_command=_execute_command(),
            ),
            question_generation_executor=executor,
            capacity_observation_repository=capacity_repository,
            workflow_unit_of_work=unit_of_work,
        )
    )

    assert result.saved_question_count == 10
    assert result.outcome_status == "succeeded"
    assert len(executor.commands) == 1
    assert executor.commands[0].dispatch_attempt_id == "attempt-1"

    assert len(capacity_repository.observations) == 1
    assert capacity_repository.observations[0].account_ref == ("groq_org_primary")

    command_types = {
        command.command_type for command in unit_of_work.command_log.appended
    }
    assert (
        WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value
    ) in command_types
    assert (
        WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value
    ) in command_types

    assert len(unit_of_work.outbox.events) == 2
    assert len(unit_of_work.timeline.entries) == 1
    assert unit_of_work.command_log.completed == [_execute_command().command_id]


@pytest.mark.asyncio
async def test_drain_dispatches_execute_when_dependencies_exist() -> None:
    executor = FakeQuestionGenerationExecutor(
        result=ExecuteWorkbenchRagEvalQuestionGenerationResult(
            dispatch_attempt_id="attempt-1",
            work_item_id="item-1",
            saved_question_count=0,
            outcome_status="retryable_failed",
            finished_at=NOW,
            capacity_observation=None,
            error_kind="transient_provider_error",
            next_attempt_at=NOW + timedelta(minutes=1),
        )
    )
    unit_of_work = FakeWorkflowUnitOfWork(
        command_log=FakeCommandLog(
            pending=(_execute_command(),),
        )
    )

    result = await DrainWorkbenchRagEvalWorkflowCommands().execute(
        DrainWorkbenchRagEvalWorkflowCommandsCommand(
            workflow_run_id="run-1",
        ),
        workflow_unit_of_work=unit_of_work,
        prepare_llm_dispatch_batch=None,
        question_generation_executor=executor,
        capacity_observation_repository=FakeCapacityRepository(),
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 1
    assert result.blocked_count == 0
    assert {command.command_type for command in unit_of_work.command_log.appended} == {
        WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value
    }
