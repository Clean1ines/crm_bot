from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_adjudication_work import (
    WorkbenchRagEvalAdjudicationPlanningInput,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.dispatch_workbench_rag_eval_workflow_command import (
    DispatchWorkbenchRagEvalWorkflowCommand,
    DispatchWorkbenchRagEvalWorkflowCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_adjudication import (
    ExecuteWorkbenchRagEvalAdjudicationCommand,
    ExecuteWorkbenchRagEvalAdjudicationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_adjudication_command import (
    HandleExecuteWorkbenchRagEvalAdjudicationCommand,
    HandleExecuteWorkbenchRagEvalAdjudicationCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_reconcile_workbench_rag_eval_adjudication_progress_command import (
    HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand,
    HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler,
    WorkbenchRagEvalAdjudicationProgressDecision,
    WorkbenchRagEvalAdjudicationProgressDecisionPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_run_workbench_rag_eval_post_promotion_verification_command import (
    RunWorkbenchRagEvalPostPromotionVerificationCommand,
    RunWorkbenchRagEvalPostPromotionVerificationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_schedule_workbench_rag_eval_adjudication_work_command import (
    HandleScheduleWorkbenchRagEvalAdjudicationWorkCommand,
    HandleScheduleWorkbenchRagEvalAdjudicationWorkCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
    WorkbenchRagEvalWorkflowEventType,
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


NOW = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)


def _command(command_type: WorkbenchRagEvalWorkflowCommandType) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}:run-1"),
        command_type=command_type.value,
        workflow_run_id="run-1",
        idempotency_key=WorkflowIdempotencyKey(f"{command_type.value}:run-1"),
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": "run-1",
            "rag_eval_run_id": "run-1",
            "project_id": "11111111-1111-1111-1111-111111111111",
            "scheduled_work_item_count": 1,
            "dispatch_attempt_id": "attempt-1",
            "work_item_id": "work-item-1",
            "revision_id": "revision-1",
            "runtime_entry_id": "runtime-entry-1",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _planning_input() -> WorkbenchRagEvalAdjudicationPlanningInput:
    return WorkbenchRagEvalAdjudicationPlanningInput(
        run_id="run-1",
        project_id="11111111-1111-1111-1111-111111111111",
        question_id="question-1",
        question="Как оплатить?",
        evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
        promotion_eligible=True,
        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        outcome_id="outcome-1",
        classification=WorkbenchRagEvalRetrievalClassification.MISS,
        expected_runtime_entry_id="entry-1",
        expected_fact_id="fact-1",
        expected_rank=None,
        expected_score=None,
        best_competitor_runtime_entry_id=None,
        best_competitor_fact_id=None,
        best_competitor_score=None,
        score_margin=None,
        target_claim="Оплатить можно картой.",
        target_possible_questions=("Как оплатить?",),
        target_exclusion_scope=None,
        target_evidence_block="Источник",
        retrieved=(),
    )


def _verification_result(
    *,
    workflow_run_id: str = "run-1",
    processed_count: int,
    remaining_count: int,
    total_query_count: int,
    terminal: bool,
    status: str,
    decision: str | None = None,
) -> RunWorkbenchRagEvalPostPromotionVerificationResult:
    return RunWorkbenchRagEvalPostPromotionVerificationResult(
        workflow_run_id=workflow_run_id,
        revision_id="revision-1",
        runtime_entry_id="runtime-entry-1",
        batch_key="revision-1:batch",
        batch_limit=20,
        processed_count=processed_count,
        remaining_count=remaining_count,
        total_query_count=total_query_count,
        terminal=terminal,
        status=status,
        decision=decision,
    )


@dataclass(slots=True)
class FakeCommandLog:
    appended: list[WorkflowCommand] = field(default_factory=list)
    completed: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        self.appended.append(command)
        return command

    async def mark_command_completed(
        self, *, command_id: WorkflowCommandId, completed_at: datetime
    ) -> WorkflowCommand:
        del completed_at
        self.completed.append(command_id)
        return _command(WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK)


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
class FakeSnapshots:
    snapshots: list[object] = field(default_factory=list)

    async def save_snapshot(self, snapshot):
        self.snapshots.append(snapshot)
        return snapshot


@dataclass(slots=True)
class FakeUow:
    command_log: FakeCommandLog = field(default_factory=FakeCommandLog)
    outbox: FakeOutbox = field(default_factory=FakeOutbox)
    timeline: FakeTimeline = field(default_factory=FakeTimeline)
    progress_snapshots: FakeSnapshots = field(default_factory=FakeSnapshots)


@dataclass(slots=True)
class FakeScheduler:
    plans: list[object] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)

    async def get_work_item(self, work_item_id: str):
        return None

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        return self.hashes.get(work_item_id)

    async def save_scheduled_work_item(
        self, *, item, idempotency_key: str, payload_hash: str, payload
    ) -> None:
        del idempotency_key, payload
        self.plans.append(item)
        self.hashes[item.work_item_id] = payload_hash


@dataclass(slots=True)
class FakePostPromotionVerificationExecutor:
    results: list[RunWorkbenchRagEvalPostPromotionVerificationResult] = field(
        default_factory=list
    )
    commands: list[RunWorkbenchRagEvalPostPromotionVerificationCommand] = field(
        default_factory=list
    )

    async def execute(
        self,
        command: RunWorkbenchRagEvalPostPromotionVerificationCommand,
    ) -> RunWorkbenchRagEvalPostPromotionVerificationResult:
        self.commands.append(command)
        if self.results:
            return self.results.pop(0)
        return _verification_result(
            workflow_run_id=command.workflow_command.workflow_run_id,
            processed_count=1,
            remaining_count=0,
            total_query_count=1,
            terminal=True,
            status="passed",
            decision="acceptable",
        )


@pytest.mark.asyncio
async def test_schedule_adjudication_creates_one_work_item_per_eligible_question() -> (
    None
):
    eligible = (_planning_input(),)
    repo = SimpleNamespace(
        list_adjudication_planning_inputs=AsyncMock(return_value=eligible),
        create_promotion_candidates_from_adjudications=AsyncMock(return_value=()),
        transition_run_progress=AsyncMock(),
    )
    scheduler = FakeScheduler()
    uow = FakeUow()

    result = (
        await HandleScheduleWorkbenchRagEvalAdjudicationWorkCommandHandler().execute(
            HandleScheduleWorkbenchRagEvalAdjudicationWorkCommand(
                _command(WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK)
            ),
            rag_eval_repository=repo,
            work_item_scheduling_repository=scheduler,
            workflow_unit_of_work=uow,
            provider_messages_builder=SimpleNamespace(
                provider_messages=lambda item: (
                    {"role": "user", "content": item.question},
                )
            ),
        )
    )

    assert result.scheduled_count == 1
    assert scheduler.plans[0].work_kind == WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND
    assert uow.command_log.appended[0].command_type == (
        WorkbenchRagEvalWorkflowCommandType.PREPARE_ADJUDICATION_DISPATCH_BATCH.value
    )


@pytest.mark.asyncio
async def test_dispatch_post_promotion_verification_uses_registered_handler() -> None:
    executor = FakePostPromotionVerificationExecutor()
    uow = FakeUow()

    result = await DispatchWorkbenchRagEvalWorkflowCommandHandler().execute(
        DispatchWorkbenchRagEvalWorkflowCommand(
            _command(
                WorkbenchRagEvalWorkflowCommandType.RUN_POST_PROMOTION_VERIFICATION
            )
        ),
        workflow_unit_of_work=uow,
        prepare_llm_dispatch_batch=None,
        post_promotion_verification_executor=executor,
    )

    assert result.dispatched is True
    assert result.blocked_reason is None
    assert result.handler_name == (
        "HandleRunWorkbenchRagEvalPostPromotionVerificationCommandHandler"
    )
    assert executor.commands[0].workflow_command.command_type == (
        WorkbenchRagEvalWorkflowCommandType.RUN_POST_PROMOTION_VERIFICATION.value
    )
    assert uow.command_log.completed == [
        executor.commands[0].workflow_command.command_id
    ]
    assert [event.event_type for event in uow.outbox.events] == [
        WorkbenchRagEvalWorkflowEventType.VERIFICATION_BATCH_COMPLETED.value,
        WorkbenchRagEvalWorkflowEventType.VERIFICATION_COMPLETED.value,
    ]
    assert uow.progress_snapshots.snapshots
    assert uow.timeline.entries


@pytest.mark.asyncio
async def test_dispatch_post_promotion_verification_appends_bounded_continuations() -> (
    None
):
    executor = FakePostPromotionVerificationExecutor(
        results=[
            _verification_result(
                processed_count=20,
                remaining_count=25,
                total_query_count=45,
                terminal=False,
                status="running",
            ),
            _verification_result(
                processed_count=20,
                remaining_count=5,
                total_query_count=45,
                terminal=False,
                status="running",
            ),
            _verification_result(
                processed_count=5,
                remaining_count=0,
                total_query_count=45,
                terminal=True,
                status="passed",
                decision="acceptable",
            ),
        ]
    )
    uow = FakeUow()
    first_command = _command(
        WorkbenchRagEvalWorkflowCommandType.RUN_POST_PROMOTION_VERIFICATION
    )

    await DispatchWorkbenchRagEvalWorkflowCommandHandler().execute(
        DispatchWorkbenchRagEvalWorkflowCommand(first_command),
        workflow_unit_of_work=uow,
        prepare_llm_dispatch_batch=None,
        post_promotion_verification_executor=executor,
    )
    await DispatchWorkbenchRagEvalWorkflowCommandHandler().execute(
        DispatchWorkbenchRagEvalWorkflowCommand(uow.command_log.appended[-1]),
        workflow_unit_of_work=uow,
        prepare_llm_dispatch_batch=None,
        post_promotion_verification_executor=executor,
    )
    await DispatchWorkbenchRagEvalWorkflowCommandHandler().execute(
        DispatchWorkbenchRagEvalWorkflowCommand(uow.command_log.appended[-1]),
        workflow_unit_of_work=uow,
        prepare_llm_dispatch_batch=None,
        post_promotion_verification_executor=executor,
    )

    assert [event.event_type for event in uow.outbox.events] == [
        WorkbenchRagEvalWorkflowEventType.VERIFICATION_BATCH_COMPLETED.value,
        WorkbenchRagEvalWorkflowEventType.VERIFICATION_BATCH_COMPLETED.value,
        WorkbenchRagEvalWorkflowEventType.VERIFICATION_BATCH_COMPLETED.value,
        WorkbenchRagEvalWorkflowEventType.VERIFICATION_COMPLETED.value,
    ]
    continuation_commands = uow.command_log.appended
    assert [command.payload["batch_index"] for command in continuation_commands] == [
        1,
        2,
    ]
    assert [command.idempotency_key.value for command in continuation_commands] == [
        "rag-eval-post-promotion-verification:revision-1:batch:1",
        "rag-eval-post-promotion-verification:revision-1:batch:2",
    ]
    assert len(uow.timeline.entries) == 1


@pytest.mark.asyncio
async def test_schedule_adjudication_zero_eligible_goes_to_promotion_review() -> None:
    repo = SimpleNamespace(
        list_adjudication_planning_inputs=AsyncMock(return_value=()),
        create_promotion_candidates_from_adjudications=AsyncMock(return_value=()),
    )
    uow = FakeUow()

    result = (
        await HandleScheduleWorkbenchRagEvalAdjudicationWorkCommandHandler().execute(
            HandleScheduleWorkbenchRagEvalAdjudicationWorkCommand(
                _command(WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK)
            ),
            rag_eval_repository=repo,
            work_item_scheduling_repository=FakeScheduler(),
            workflow_unit_of_work=uow,
            provider_messages_builder=SimpleNamespace(
                provider_messages=lambda item: ()
            ),
        )
    )

    assert result.scheduled_count == 0
    repo.create_promotion_candidates_from_adjudications.assert_awaited_once()
    assert uow.command_log.appended == []
    assert uow.outbox.events[-1].event_type == "RagEvalPromotionCandidatesReady"


@dataclass(slots=True)
class FakeAdjudicationExecutor:
    result: ExecuteWorkbenchRagEvalAdjudicationResult
    commands: list[ExecuteWorkbenchRagEvalAdjudicationCommand] = field(
        default_factory=list
    )

    async def execute(
        self, command: ExecuteWorkbenchRagEvalAdjudicationCommand
    ) -> ExecuteWorkbenchRagEvalAdjudicationResult:
        self.commands.append(command)
        return self.result


@pytest.mark.asyncio
async def test_execute_adjudication_handler_records_capacity_and_reconcile() -> None:
    executor = FakeAdjudicationExecutor(
        ExecuteWorkbenchRagEvalAdjudicationResult(
            dispatch_attempt_id="attempt-1",
            work_item_id="work-item-1",
            saved_adjudication_count=1,
            outcome_status="succeeded",
            finished_at=NOW,
            capacity_observation={
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "remaining_minute_requests": 1,
                "remaining_minute_tokens": 1,
                "remaining_daily_requests": 1,
                "remaining_daily_tokens": 1,
                "outcome_class": "succeeded",
                "observed_at": NOW,
            },
            error_kind=None,
            next_attempt_at=None,
        )
    )
    capacity_repo = SimpleNamespace(record_observation=AsyncMock())
    uow = FakeUow()

    result = await HandleExecuteWorkbenchRagEvalAdjudicationCommandHandler().execute(
        HandleExecuteWorkbenchRagEvalAdjudicationCommand(
            _command(WorkbenchRagEvalWorkflowCommandType.EXECUTE_ADJUDICATION)
        ),
        adjudication_executor=executor,
        capacity_observation_repository=capacity_repo,
        workflow_unit_of_work=uow,
    )

    assert result.saved_adjudication_count == 1
    capacity_repo.record_observation.assert_awaited_once()
    assert uow.command_log.appended[-1].command_type == (
        WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS.value
    )
    assert uow.command_log.completed == [
        _command(WorkbenchRagEvalWorkflowCommandType.EXECUTE_ADJUDICATION).command_id
    ]


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
    ("summary", "covered", "expected"),
    (
        (
            _summary(ready_count=1, total_count=1),
            False,
            WorkbenchRagEvalAdjudicationProgressDecision.PREPARE_NEXT_BATCH_NOW,
        ),
        (
            _summary(
                retryable_failed_count=1,
                total_count=1,
                next_due_at=NOW + timedelta(minutes=1),
            ),
            False,
            WorkbenchRagEvalAdjudicationProgressDecision.PREPARE_NEXT_BATCH_LATER,
        ),
        (
            _summary(leased_count=1, total_count=1),
            False,
            WorkbenchRagEvalAdjudicationProgressDecision.WAIT_FOR_ACTIVE_ATTEMPTS,
        ),
        (
            _summary(completed_count=1, total_count=1),
            True,
            WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_DRAINED,
        ),
        (
            _summary(terminal_failed_count=1, total_count=1),
            False,
            WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_BLOCKED,
        ),
    ),
)
def test_adjudication_reconcile_decision_matrix(
    summary: WorkItemProgressSummary,
    covered: bool,
    expected: WorkbenchRagEvalAdjudicationProgressDecision,
) -> None:
    result = WorkbenchRagEvalAdjudicationProgressDecisionPolicy().decide(
        summary=summary,
        now=NOW,
        adjudication_persistence_complete=covered,
        zero_eligible_fast_path=False,
    )

    assert result.decision is expected


@pytest.mark.asyncio
async def test_reconcile_drained_creates_candidates_and_promotion_review() -> None:
    current = _command(
        WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS
    )
    repo = SimpleNamespace(
        has_adjudications_for_all_eligible_questions=AsyncMock(return_value=True),
        create_promotion_candidates_from_adjudications=AsyncMock(
            return_value=(object(), object())
        ),
        transition_run_progress=AsyncMock(),
    )
    uow = FakeUow()

    result = await HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler().execute(
        HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand(current),
        work_item_progress_read_repository=SimpleNamespace(
            summarize_by_work_kind_and_workflow=AsyncMock(
                return_value=_summary(completed_count=2, total_count=2)
            )
        ),
        adjudication_coverage_repository=repo,
        rag_eval_repository=repo,
        workflow_unit_of_work=uow,
    )

    assert result.promotion_candidate_count == 2
    repo.create_promotion_candidates_from_adjudications.assert_awaited_once()
    assert uow.outbox.events[-1].event_type == "RagEvalPromotionCandidatesReady"


@pytest.mark.asyncio
async def test_dispatcher_runs_schedule_adjudication_when_dependencies_exist() -> None:
    repo = SimpleNamespace(
        list_adjudication_planning_inputs=AsyncMock(return_value=()),
        create_promotion_candidates_from_adjudications=AsyncMock(return_value=()),
    )
    result = await DispatchWorkbenchRagEvalWorkflowCommandHandler().execute(
        DispatchWorkbenchRagEvalWorkflowCommand(
            _command(WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK)
        ),
        workflow_unit_of_work=FakeUow(),
        prepare_llm_dispatch_batch=None,
        rag_eval_repository=repo,
        work_item_scheduling_repository=FakeScheduler(),
        adjudication_provider_messages_builder=SimpleNamespace(
            provider_messages=lambda item: ()
        ),
    )

    assert result.dispatched is True
    assert (
        result.handler_name
        == "HandleScheduleWorkbenchRagEvalAdjudicationWorkCommandHandler"
    )
