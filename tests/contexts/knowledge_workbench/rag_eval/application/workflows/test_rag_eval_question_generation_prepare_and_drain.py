from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.workflows.drain_workbench_rag_eval_workflow_commands import (
    DrainWorkbenchRagEvalWorkflowCommands,
    DrainWorkbenchRagEvalWorkflowCommandsCommand,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_prepare_workbench_rag_eval_question_generation_dispatch_batch import (
    HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommand,
    HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
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
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)


def _now() -> datetime:
    return datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


def _prepare_command() -> WorkflowCommand:
    now = _now()
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:prepare-rag-eval-qgen:run-1"),
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value
        ),
        workflow_run_id="run-1",
        idempotency_key=WorkflowIdempotencyKey("prepare-rag-eval-qgen:run-1"),
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": "run-1",
            "project_id": "project-1",
            "publication_id": None,
            "source_document_ref": None,
            "scheduled_work_item_count": 2,
            "active_model_ref": "qwen/qwen3.6-27b",
            "work_kind": (WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=now,
        created_at=now,
        updated_at=now,
    )


@dataclass(slots=True)
class FakePrepare:
    result: object
    commands: list[PrepareLlmDispatchBatchCommand] = field(default_factory=list)

    async def execute(
        self,
        command: PrepareLlmDispatchBatchCommand,
    ) -> object:
        self.commands.append(command)
        return self.result


@dataclass(slots=True)
class FakeCommandLog:
    pending: tuple[WorkflowCommand, ...] = ()
    appended: list[WorkflowCommand] = field(default_factory=list)
    completed: list[WorkflowCommandId] = field(default_factory=list)
    rescheduled: list[tuple[WorkflowCommandId, datetime]] = field(default_factory=list)

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
        return _prepare_command()

    async def reschedule_pending_command(
        self,
        *,
        command_id: WorkflowCommandId,
        run_after: datetime,
        rescheduled_at: datetime,
    ) -> WorkflowCommand:
        del rescheduled_at
        self.rescheduled.append((command_id, run_after))
        return _prepare_command()


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


def _started_attempt(
    *,
    attempt_id: str,
    work_item_id: str,
    account_ref: str,
) -> object:
    return SimpleNamespace(
        attempt_id=attempt_id,
        work_item_id=work_item_id,
        attempt_number=1,
        dispatch_payload={
            "llm_allocation": {
                "provider": "groq",
                "account_ref": account_ref,
                "model_ref": "qwen/qwen3.6-27b",
            },
            "schedule_payload": {
                "workflow_run_id": "run-1",
            },
        },
    )


@pytest.mark.asyncio
async def test_prepare_handler_uses_canonical_prepare_and_appends_execute_commands() -> (
    None
):
    prepare = FakePrepare(
        result=SimpleNamespace(
            attempt_result=SimpleNamespace(
                started_attempts=(
                    _started_attempt(
                        attempt_id="attempt-1",
                        work_item_id="item-1",
                        account_ref="groq_org_primary",
                    ),
                    _started_attempt(
                        attempt_id="attempt-2",
                        work_item_id="item-2",
                        account_ref="groq_org_secondary",
                    ),
                )
            ),
            capacity_retry_at=None,
        )
    )
    unit_of_work = FakeWorkflowUnitOfWork(
        command_log=FakeCommandLog(),
    )

    result = await HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommandHandler().execute(
        HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommand(
            workflow_command=_prepare_command(),
        ),
        prepare_llm_dispatch_batch=prepare,
        workflow_unit_of_work=unit_of_work,
    )

    assert result.prepared_dispatch_count == 2
    assert len(prepare.commands) == 1
    assert prepare.commands[0].work_kind == (
        WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND
    )
    assert prepare.commands[0].requested_items == 2
    assert prepare.commands[0].active_model_ref == "qwen/qwen3.6-27b"
    assert prepare.commands[0].allow_automatic_fallbacks is True

    assert len(unit_of_work.command_log.appended) == 2
    assert {command.command_type for command in unit_of_work.command_log.appended} == {
        WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION.value
    }
    assert {
        command.payload["dispatch_attempt_id"]
        for command in unit_of_work.command_log.appended
    } == {"attempt-1", "attempt-2"}
    assert len(unit_of_work.outbox.events) == 3
    assert unit_of_work.command_log.completed == [_prepare_command().command_id]


@pytest.mark.asyncio
async def test_prepare_handler_reschedules_same_command_on_capacity_retry() -> None:
    retry_at = _now() + timedelta(minutes=1)
    prepare = FakePrepare(
        result=SimpleNamespace(
            attempt_result=SimpleNamespace(started_attempts=()),
            capacity_retry_at=retry_at,
        )
    )
    unit_of_work = FakeWorkflowUnitOfWork(
        command_log=FakeCommandLog(),
    )

    result = await HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommandHandler().execute(
        HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommand(
            workflow_command=_prepare_command(),
        ),
        prepare_llm_dispatch_batch=prepare,
        workflow_unit_of_work=unit_of_work,
    )

    assert result.prepared_dispatch_count == 0
    assert result.rescheduled_at is not None
    assert unit_of_work.command_log.completed == []
    assert len(unit_of_work.command_log.rescheduled) == 1
    assert unit_of_work.command_log.appended == []
    assert len(unit_of_work.timeline.entries) == 1


@pytest.mark.asyncio
async def test_drain_dispatches_rag_eval_prepare_command() -> None:
    prepare = FakePrepare(
        result=SimpleNamespace(
            attempt_result=SimpleNamespace(
                started_attempts=(
                    _started_attempt(
                        attempt_id="attempt-1",
                        work_item_id="item-1",
                        account_ref="groq_org_primary",
                    ),
                )
            ),
            capacity_retry_at=None,
        )
    )
    unit_of_work = FakeWorkflowUnitOfWork(
        command_log=FakeCommandLog(
            pending=(_prepare_command(),),
        )
    )

    result = await DrainWorkbenchRagEvalWorkflowCommands().execute(
        DrainWorkbenchRagEvalWorkflowCommandsCommand(
            workflow_run_id="run-1",
            max_commands=10,
        ),
        workflow_unit_of_work=unit_of_work,
        prepare_llm_dispatch_batch=prepare,
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 1
    assert result.blocked_count == 0


@pytest.mark.asyncio
async def test_drain_blocks_unimplemented_rag_eval_command_explicitly() -> None:
    now = _now()
    execute_command = WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:execute-rag-eval-qgen:run-1"),
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION.value
        ),
        workflow_run_id="run-1",
        idempotency_key=WorkflowIdempotencyKey("execute-rag-eval-qgen:run-1"),
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": "run-1",
            "project_id": "project-1",
            "dispatch_attempt_id": "attempt-1",
            "work_item_id": "item-1",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=now,
        created_at=now,
        updated_at=now,
    )
    unit_of_work = FakeWorkflowUnitOfWork(
        command_log=FakeCommandLog(
            pending=(execute_command,),
        )
    )

    result = await DrainWorkbenchRagEvalWorkflowCommands().execute(
        DrainWorkbenchRagEvalWorkflowCommandsCommand(
            workflow_run_id="run-1",
        ),
        workflow_unit_of_work=unit_of_work,
        prepare_llm_dispatch_batch=None,
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 0
    assert result.blocked_count == 1
    assert result.last_blocked_command_type == (
        WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION.value
    )
    assert result.last_blocked_reason == ("RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED")


@pytest.mark.asyncio
async def test_drain_stops_on_unimplemented_later_command_without_busy_loop() -> None:
    now = _now()
    adjudication_command = WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:schedule-adjudication:run-1"),
        command_type=WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK.value,
        workflow_run_id="run-1",
        idempotency_key=WorkflowIdempotencyKey("schedule-adjudication:run-1"),
        payload={"workflow_run_id": "run-1"},
        status=WorkflowCommandStatus.PENDING,
        run_after=now,
        created_at=now,
        updated_at=now,
    )
    unit_of_work = FakeWorkflowUnitOfWork(
        command_log=FakeCommandLog(
            pending=(adjudication_command, _prepare_command()),
        )
    )

    result = await DrainWorkbenchRagEvalWorkflowCommands().execute(
        DrainWorkbenchRagEvalWorkflowCommandsCommand(
            workflow_run_id="run-1",
            max_commands=10,
        ),
        workflow_unit_of_work=unit_of_work,
        prepare_llm_dispatch_batch=FakePrepare(result=SimpleNamespace()),
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 0
    assert result.blocked_count == 1
    assert result.last_blocked_command_type == (
        WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK.value
    )
    assert unit_of_work.command_log.completed == []
