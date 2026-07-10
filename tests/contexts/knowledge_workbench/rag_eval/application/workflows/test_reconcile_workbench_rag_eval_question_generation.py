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
