from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_reconcile_workbench_rag_eval_question_generation_progress_command import (
    HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand,
    HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler,
    WorkbenchRagEvalQuestionGenerationProgressDecision,
    WorkbenchRagEvalQuestionGenerationProgressDecisionPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.drain_workbench_rag_eval_workflow_commands import (
    DrainWorkbenchRagEvalWorkflowCommands,
    DrainWorkbenchRagEvalWorkflowCommandsCommand,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRunStatus,
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


NOW = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)


def _summary(**overrides: object) -> WorkItemProgressSummary:
    values = dict(
        ready_count=0,
        leased_count=0,
        deferred_count=0,
        retryable_failed_count=0,
        completed_count=0,
        terminal_failed_count=0,
        cancelled_count=0,
        split_superseded_count=0,
        user_action_required_count=0,
        total_count=0,
        next_due_at=None,
        due_deferred_count=0,
        due_retryable_failed_count=0,
    )
    values.update(overrides)
    return WorkItemProgressSummary(**values)  # type: ignore[arg-type]


class FakeCommandLog:
    def __init__(self, command: WorkflowCommand) -> None:
        self.command = command
        self.list_calls = 0
        self.failed_commands: list[WorkflowCommandId] = []

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        del limit
        self.list_calls += 1
        if (
            self.command.workflow_run_id == workflow_run_id
            and self.command.status is WorkflowCommandStatus.PENDING
            and self.command.run_after <= NOW
        ):
            return (self.command,)
        return ()

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        if command_id != self.command.command_id:
            raise KeyError(command_id.value)
        self.command = WorkflowCommand(
            command_id=self.command.command_id,
            command_type=self.command.command_type,
            workflow_run_id=self.command.workflow_run_id,
            idempotency_key=self.command.idempotency_key,
            payload=self.command.payload,
            status=WorkflowCommandStatus.COMPLETED,
            run_after=self.command.run_after,
            created_at=self.command.created_at,
            updated_at=NOW,
            attempt_count=self.command.attempt_count,
        )
        return self.command

    async def mark_command_failed(
        self,
        *,
        command_id: WorkflowCommandId,
        failed_at: datetime,
    ) -> WorkflowCommand:
        if command_id != self.command.command_id:
            raise KeyError(command_id.value)
        self.failed_commands.append(command_id)
        self.command = WorkflowCommand(
            command_id=self.command.command_id,
            command_type=self.command.command_type,
            workflow_run_id=self.command.workflow_run_id,
            idempotency_key=self.command.idempotency_key,
            payload=self.command.payload,
            status=WorkflowCommandStatus.FAILED,
            run_after=self.command.run_after,
            created_at=self.command.created_at,
            updated_at=failed_at,
            attempt_count=self.command.attempt_count,
        )
        return self.command


class FailingCoverageRepository:
    def __init__(self) -> None:
        self.calls = 0

    async def has_complete_question_sets(
        self,
        *,
        rag_eval_run_id: str,
        expected_entry_count: int,
        questions_per_entry: int,
    ) -> bool:
        del rag_eval_run_id, expected_entry_count, questions_per_entry
        self.calls += 1
        raise TypeError("total_questions must be int")


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (
            _summary(ready_count=1, total_count=1),
            WorkbenchRagEvalQuestionGenerationProgressDecision.PREPARE_NEXT_BATCH_NOW,
        ),
        (
            _summary(leased_count=1, total_count=1),
            WorkbenchRagEvalQuestionGenerationProgressDecision.WAIT_FOR_ACTIVE_ATTEMPTS,
        ),
        (
            _summary(terminal_failed_count=1, total_count=1),
            WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_BLOCKED,
        ),
        (
            _summary(),
            WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_BLOCKED,
        ),
    ],
)
def test_policy_core_decisions(
    summary: WorkItemProgressSummary, expected: object
) -> None:
    result = WorkbenchRagEvalQuestionGenerationProgressDecisionPolicy().decide(
        summary=summary, now=NOW, domain_persistence_complete=False
    )
    assert result.decision is expected


def test_policy_preserves_exact_future_due_time() -> None:
    due = NOW + timedelta(minutes=3)
    result = WorkbenchRagEvalQuestionGenerationProgressDecisionPolicy().decide(
        summary=_summary(retryable_failed_count=1, total_count=1, next_due_at=due),
        now=NOW,
        domain_persistence_complete=False,
    )
    assert (
        result.decision
        is WorkbenchRagEvalQuestionGenerationProgressDecision.PREPARE_NEXT_BATCH_LATER
    )
    assert result.next_due_at == due


def test_policy_blocks_completed_work_with_missing_questions() -> None:
    result = WorkbenchRagEvalQuestionGenerationProgressDecisionPolicy().decide(
        summary=_summary(completed_count=2, total_count=2),
        now=NOW,
        domain_persistence_complete=False,
    )
    assert (
        result.decision
        is WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_BLOCKED
    )


def test_policy_drains_only_complete_generic_and_domain_coverage() -> None:
    result = WorkbenchRagEvalQuestionGenerationProgressDecisionPolicy().decide(
        summary=_summary(completed_count=2, total_count=2),
        now=NOW,
        domain_persistence_complete=True,
    )
    assert (
        result.decision
        is WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_DRAINED
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("summary", "complete", "status", "phase"),
    [
        (
            _summary(ready_count=1, total_count=1),
            False,
            WorkbenchRagEvalRunStatus.RUNNING,
            WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION,
        ),
        (
            _summary(
                retryable_failed_count=1,
                total_count=1,
                next_due_at=NOW + timedelta(minutes=1),
            ),
            False,
            WorkbenchRagEvalRunStatus.WAITING_CAPACITY,
            WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION,
        ),
        (
            _summary(leased_count=1, total_count=1),
            False,
            WorkbenchRagEvalRunStatus.RUNNING,
            WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION,
        ),
        (
            _summary(terminal_failed_count=1, total_count=1),
            False,
            WorkbenchRagEvalRunStatus.BLOCKED,
            WorkbenchRagEvalCurrentPhase.BLOCKED,
        ),
        (
            _summary(completed_count=1, total_count=1),
            True,
            WorkbenchRagEvalRunStatus.RUNNING,
            WorkbenchRagEvalCurrentPhase.RETRIEVAL_EVALUATION,
        ),
    ],
)
async def test_handler_persists_transition_matrix(
    summary, complete, status, phase
) -> None:
    workflow_id, rag_id = "workflow-run-1", "rag-run-9"
    current = WorkflowCommand(
        command_id=WorkflowCommandId("command:reconcile"),
        command_type=WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value,
        workflow_run_id=workflow_id,
        idempotency_key=WorkflowIdempotencyKey("reconcile"),
        payload={
            "workflow_run_id": workflow_id,
            "rag_eval_run_id": rag_id,
            "project_id": "project-1",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    repo = SimpleNamespace(transition_run_progress=AsyncMock())
    uow = SimpleNamespace(
        command_log=SimpleNamespace(
            append_pending_command=AsyncMock(), mark_command_completed=AsyncMock()
        ),
        outbox=SimpleNamespace(append_event=AsyncMock(side_effect=lambda event: event)),
        progress_snapshots=SimpleNamespace(save_snapshot=AsyncMock()),
        timeline=SimpleNamespace(append_entry=AsyncMock()),
    )
    await HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler().execute(
        HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand(current),
        work_item_progress_read_repository=SimpleNamespace(
            summarize_by_work_kind_and_workflow=AsyncMock(return_value=summary)
        ),
        question_coverage_repository=SimpleNamespace(
            has_complete_question_sets=AsyncMock(return_value=complete)
        ),
        rag_eval_repository=repo,
        workflow_unit_of_work=uow,
    )
    transition = repo.transition_run_progress.await_args.kwargs
    assert (
        transition["run_id"],
        transition["status"],
        transition["current_phase"],
    ) == (rag_id, status, phase)


@pytest.mark.asyncio
async def test_drain_marks_poison_reconcile_command_failed_and_does_not_reclaim_immediately() -> (
    None
):
    workflow_id, rag_id = "workflow-run-poison", "rag-run-poison"
    current = WorkflowCommand(
        command_id=WorkflowCommandId("command:poison-reconcile"),
        command_type=WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value,
        workflow_run_id=workflow_id,
        idempotency_key=WorkflowIdempotencyKey("poison-reconcile"),
        payload={
            "workflow_run_id": workflow_id,
            "rag_eval_run_id": rag_id,
            "project_id": "project-1",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    command_log = FakeCommandLog(current)
    coverage = FailingCoverageRepository()
    uow = SimpleNamespace(
        command_log=command_log,
        outbox=SimpleNamespace(append_event=AsyncMock(side_effect=lambda event: event)),
        progress_snapshots=SimpleNamespace(save_snapshot=AsyncMock()),
        timeline=SimpleNamespace(append_entry=AsyncMock()),
    )

    first = await DrainWorkbenchRagEvalWorkflowCommands().execute(
        DrainWorkbenchRagEvalWorkflowCommandsCommand(
            workflow_run_id=workflow_id,
            max_commands=10,
        ),
        workflow_unit_of_work=uow,
        prepare_llm_dispatch_batch=SimpleNamespace(),
        work_item_progress_read_repository=SimpleNamespace(
            summarize_by_work_kind_and_workflow=AsyncMock(
                return_value=_summary(completed_count=1, total_count=1)
            )
        ),
        question_coverage_repository=coverage,
        rag_eval_repository=SimpleNamespace(transition_run_progress=AsyncMock()),
    )
    second = await DrainWorkbenchRagEvalWorkflowCommands().execute(
        DrainWorkbenchRagEvalWorkflowCommandsCommand(
            workflow_run_id=workflow_id,
            max_commands=10,
        ),
        workflow_unit_of_work=uow,
        prepare_llm_dispatch_batch=SimpleNamespace(),
        work_item_progress_read_repository=SimpleNamespace(
            summarize_by_work_kind_and_workflow=AsyncMock(
                return_value=_summary(completed_count=1, total_count=1)
            )
        ),
        question_coverage_repository=coverage,
        rag_eval_repository=SimpleNamespace(transition_run_progress=AsyncMock()),
    )

    assert command_log.command.status is WorkflowCommandStatus.FAILED
    assert tuple(command_log.failed_commands) == (current.command_id,)
    assert coverage.calls == 1
    assert first.inspected_count == 1
    assert first.dispatched_count == 0
    assert first.blocked_count == 1
    assert first.last_blocked_command_type == current.command_type
    assert first.last_blocked_reason == "handler_failed:TypeError"
    assert second.inspected_count == 0
    assert second.dispatched_count == 0
    assert second.blocked_count == 0
