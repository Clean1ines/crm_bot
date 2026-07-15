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
    WorkbenchRagEvalWorkflowCommandHandlerFailed,
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


def _progress_repo(
    summary: WorkItemProgressSummary,
    *,
    revision: str = "revision-alpha",
) -> SimpleNamespace:
    return SimpleNamespace(
        summarize_by_work_kind_and_workflow=AsyncMock(return_value=summary),
        prepare_iteration_revision=AsyncMock(return_value=revision),
    )


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


class StrictIdempotentCommandLog:
    def __init__(self) -> None:
        self.commands_by_key: dict[str, WorkflowCommand] = {}
        self.appended_commands: list[WorkflowCommand] = []
        self.completed_commands: list[WorkflowCommandId] = []

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        existing = self.commands_by_key.get(command.idempotency_key.value)
        if existing is not None:
            if existing.command_type != command.command_type:
                raise ValueError("idempotency_key conflict has different command_type")
            if existing.workflow_run_id != command.workflow_run_id:
                raise ValueError(
                    "idempotency_key conflict has different workflow_run_id"
                )
            if dict(existing.payload) != dict(command.payload):
                raise ValueError("idempotency_key conflict has different payload")
            return existing
        self.commands_by_key[command.idempotency_key.value] = command
        self.appended_commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed_commands.append(command_id)
        return WorkflowCommand(
            command_id=command_id,
            command_type="completed-placeholder",
            workflow_run_id="workflow-run-1",
            idempotency_key=WorkflowIdempotencyKey(f"completed:{command_id.value}"),
            payload={"workflow_run_id": "workflow-run-1"},
            status=WorkflowCommandStatus.COMPLETED,
            run_after=NOW,
            created_at=NOW,
            updated_at=NOW,
        )


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


def _qgen_reconcile_command(
    *,
    command_id: str,
    causation_dispatch_attempt_id: str,
    causation_work_item_id: str,
    outcome_status: str = "succeeded",
    updated_at: datetime = NOW,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(command_id),
        command_type=WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value,
        workflow_run_id="workflow-run-1",
        idempotency_key=WorkflowIdempotencyKey(command_id),
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": "workflow-run-1",
            "rag_eval_run_id": "workflow-run-1",
            "project_id": "project-1",
            "publication_id": "publication-1",
            "source_document_ref": "source-document-1",
            "work_kind": "knowledge_workbench.rag_eval.question_generation",
            "causation_dispatch_attempt_id": causation_dispatch_attempt_id,
            "causation_work_item_id": causation_work_item_id,
            "outcome_status": outcome_status,
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=updated_at,
        created_at=updated_at,
        updated_at=updated_at,
    )


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
        work_item_progress_read_repository=_progress_repo(summary),
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
async def test_reconcile_next_prepare_is_idempotent_across_attempt_signal_payloads() -> (
    None
):
    command_log = StrictIdempotentCommandLog()
    uow = SimpleNamespace(
        command_log=command_log,
        outbox=SimpleNamespace(append_event=AsyncMock(side_effect=lambda event: event)),
        progress_snapshots=SimpleNamespace(save_snapshot=AsyncMock()),
        timeline=SimpleNamespace(append_entry=AsyncMock()),
    )
    summary = _summary(ready_count=8, total_count=8)
    handler = HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler()

    for index in range(2):
        await handler.execute(
            HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand(
                _qgen_reconcile_command(
                    command_id=f"command:reconcile:{index}",
                    causation_dispatch_attempt_id=f"attempt-{index}",
                    causation_work_item_id=f"work-item-{index}",
                )
            ),
            work_item_progress_read_repository=_progress_repo(summary),
            question_coverage_repository=SimpleNamespace(
                has_complete_question_sets=AsyncMock(return_value=False)
            ),
            rag_eval_repository=SimpleNamespace(transition_run_progress=AsyncMock()),
            workflow_unit_of_work=uow,
        )

    assert len(command_log.appended_commands) == 1
    next_command = command_log.appended_commands[0]
    assert (
        next_command.command_type
        == WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value
    )
    assert next_command.payload["scheduled_work_item_count"] == 8
    assert "causation_dispatch_attempt_id" not in next_command.payload
    assert "causation_work_item_id" not in next_command.payload
    assert "outcome_status" not in next_command.payload


@pytest.mark.asyncio
async def test_reconcile_next_prepare_keys_requested_count_revision() -> None:
    command_log = StrictIdempotentCommandLog()
    uow = SimpleNamespace(
        command_log=command_log,
        outbox=SimpleNamespace(append_event=AsyncMock(side_effect=lambda event: event)),
        progress_snapshots=SimpleNamespace(save_snapshot=AsyncMock()),
        timeline=SimpleNamespace(append_entry=AsyncMock()),
    )
    handler = HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler()

    for index, summary in enumerate(
        (
            _summary(ready_count=8, total_count=8),
            _summary(ready_count=4, completed_count=4, total_count=8),
        )
    ):
        await handler.execute(
            HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand(
                _qgen_reconcile_command(
                    command_id=f"command:reconcile:progress:{index}",
                    causation_dispatch_attempt_id=f"attempt-progress-{index}",
                    causation_work_item_id=f"work-item-progress-{index}",
                )
            ),
            work_item_progress_read_repository=_progress_repo(
                summary, revision=f"revision-progress-{index}"
            ),
            question_coverage_repository=SimpleNamespace(
                has_complete_question_sets=AsyncMock(return_value=False)
            ),
            rag_eval_repository=SimpleNamespace(transition_run_progress=AsyncMock()),
            workflow_unit_of_work=uow,
        )

    assert len(command_log.appended_commands) == 2
    assert {
        command.payload["scheduled_work_item_count"]
        for command in command_log.appended_commands
    } == {8, 4}
    assert len(command_log.commands_by_key) == 2


@pytest.mark.asyncio
async def test_reconcile_next_prepare_deduplicates_same_count_across_reconcile_times() -> (
    None
):
    command_log = StrictIdempotentCommandLog()
    uow = SimpleNamespace(
        command_log=command_log,
        outbox=SimpleNamespace(append_event=AsyncMock(side_effect=lambda event: event)),
        progress_snapshots=SimpleNamespace(save_snapshot=AsyncMock()),
        timeline=SimpleNamespace(append_entry=AsyncMock()),
    )
    handler = HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler()

    for index, updated_at in enumerate((NOW, NOW + timedelta(seconds=37))):
        await handler.execute(
            HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand(
                _qgen_reconcile_command(
                    command_id=f"command:reconcile:same-count:{index}",
                    causation_dispatch_attempt_id=f"attempt-same-count-{index}",
                    causation_work_item_id=f"work-item-same-count-{index}",
                    updated_at=updated_at,
                )
            ),
            work_item_progress_read_repository=_progress_repo(
                _summary(ready_count=8, total_count=8),
                revision="same-due-set-attempt-generation",
            ),
            question_coverage_repository=SimpleNamespace(
                has_complete_question_sets=AsyncMock(return_value=False)
            ),
            rag_eval_repository=SimpleNamespace(transition_run_progress=AsyncMock()),
            workflow_unit_of_work=uow,
        )

    assert len(command_log.appended_commands) == 1
    assert len(command_log.commands_by_key) == 1
    next_command = command_log.appended_commands[0]
    assert next_command.idempotency_key.value.endswith(
        ":PrepareRagEvalQuestionGenerationDispatchBatch:"
        "scheduled:8:revision:same-due-set-attempt-generation"
    )


@pytest.mark.asyncio
async def test_reconcile_next_prepare_allows_repeated_count_after_new_attempt_generation() -> (
    None
):
    command_log = StrictIdempotentCommandLog()
    uow = SimpleNamespace(
        command_log=command_log,
        outbox=SimpleNamespace(append_event=AsyncMock(side_effect=lambda event: event)),
        progress_snapshots=SimpleNamespace(save_snapshot=AsyncMock()),
        timeline=SimpleNamespace(append_entry=AsyncMock()),
    )
    handler = HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler()
    summary = _summary(ready_count=4, completed_count=4, total_count=8)

    for revision in ("work-items-attempt-1", "work-items-attempt-2"):
        await handler.execute(
            HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand(
                _qgen_reconcile_command(
                    command_id=f"command:reconcile:{revision}",
                    causation_dispatch_attempt_id=f"attempt:{revision}",
                    causation_work_item_id=f"work-item:{revision}",
                )
            ),
            work_item_progress_read_repository=_progress_repo(
                summary, revision=revision
            ),
            question_coverage_repository=SimpleNamespace(
                has_complete_question_sets=AsyncMock(return_value=False)
            ),
            rag_eval_repository=SimpleNamespace(transition_run_progress=AsyncMock()),
            workflow_unit_of_work=uow,
        )
        await command_log.mark_command_completed(
            command_id=command_log.appended_commands[-1].command_id,
            completed_at=NOW,
        )

    assert len(command_log.appended_commands) == 2
    assert [
        command.payload["scheduled_work_item_count"]
        for command in command_log.appended_commands
    ] == [4, 4]
    assert len(command_log.commands_by_key) == 2
    assert {
        command.idempotency_key.value.rsplit(":revision:", maxsplit=1)[1]
        for command in command_log.appended_commands
    } == {"work-items-attempt-1", "work-items-attempt-2"}


@pytest.mark.asyncio
async def test_reconcile_lifecycle_partial_then_complete_moves_to_retrieval() -> None:
    command_log = StrictIdempotentCommandLog()
    repo = SimpleNamespace(transition_run_progress=AsyncMock())
    projected_events: list[object] = []
    uow = SimpleNamespace(
        command_log=command_log,
        outbox=SimpleNamespace(append_event=AsyncMock(side_effect=lambda event: event)),
        progress_snapshots=SimpleNamespace(save_snapshot=AsyncMock()),
        timeline=SimpleNamespace(append_entry=AsyncMock()),
    )
    frontend_projection_writer = SimpleNamespace(
        execute=AsyncMock(side_effect=lambda event: projected_events.append(event))
    )
    handler = HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler()
    scenarios = (
        (_summary(ready_count=8, total_count=8), False),
        (_summary(ready_count=4, completed_count=4, total_count=8), False),
        (_summary(completed_count=8, total_count=8), True),
    )

    for index, (summary, complete) in enumerate(scenarios):
        await handler.execute(
            HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand(
                _qgen_reconcile_command(
                    command_id=f"command:reconcile:lifecycle:{index}",
                    causation_dispatch_attempt_id=f"attempt-lifecycle-{index}",
                    causation_work_item_id=f"work-item-lifecycle-{index}",
                )
            ),
            work_item_progress_read_repository=_progress_repo(
                summary, revision=f"revision-lifecycle-{index}"
            ),
            question_coverage_repository=SimpleNamespace(
                has_complete_question_sets=AsyncMock(return_value=complete)
            ),
            rag_eval_repository=repo,
            workflow_unit_of_work=uow,
            frontend_event_projection_writer=frontend_projection_writer,
        )

    assert [command.command_type for command in command_log.appended_commands] == [
        WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value,
        WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value,
        WorkbenchRagEvalWorkflowCommandType.RUN_RETRIEVAL_EVALUATION.value,
    ]
    final_transition = repo.transition_run_progress.await_args_list[-1].kwargs
    assert final_transition["current_phase"] is (
        WorkbenchRagEvalCurrentPhase.RETRIEVAL_EVALUATION
    )
    assert frontend_projection_writer.execute.await_count == 4
    assert all(
        getattr(event, "payload")["project_id"] == "project-1"
        for event in projected_events
    )


@pytest.mark.asyncio
async def test_drain_reports_poison_reconcile_command_without_mutating_current_transaction() -> (
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

    with pytest.raises(WorkbenchRagEvalWorkflowCommandHandlerFailed) as exc_info:
        await DrainWorkbenchRagEvalWorkflowCommands().execute(
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

    assert exc_info.value.workflow_command.command_id == current.command_id
    assert isinstance(exc_info.value.cause, TypeError)
    assert command_log.command.status is WorkflowCommandStatus.PENDING
    assert command_log.failed_commands == []
    assert coverage.calls == 1
