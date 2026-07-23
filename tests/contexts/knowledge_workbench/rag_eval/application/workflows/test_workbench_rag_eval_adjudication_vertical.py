from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalAdjudication,
    WorkbenchRagEvalAdjudicationVerdict,
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
    WorkbenchRagEvalRunStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_adjudication_output_validation_policy import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION,
    WorkbenchRagEvalAdjudicationOutputValidationOutcome,
    WorkbenchRagEvalAdjudicationOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_reconcile_workbench_rag_eval_adjudication_progress_command import (
    HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand,
    HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler,
    WorkbenchRagEvalAdjudicationProgressDecision,
    WorkbenchRagEvalAdjudicationProgressDecisionPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_adjudication_work import (
    ADJUDICATION_PROMPT_VERSION,
    WorkbenchRagEvalAdjudicationEligibilityPolicy,
    WorkbenchRagEvalAdjudicationPlanningInput,
    WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot,
    WorkbenchRagEvalAdjudicationWorkPlanner,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    model_budget_profile_for_ref,
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


def _input(
    *,
    role: WorkbenchRagEvalQuestionRole = WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
    promotion_eligible: bool = True,
    risk: WorkbenchRagEvalQuestionAmbiguityRisk | None = (
        WorkbenchRagEvalQuestionAmbiguityRisk.LOW
    ),
    classification: WorkbenchRagEvalRetrievalClassification = (
        WorkbenchRagEvalRetrievalClassification.MISS
    ),
    question_id: str = "question-1",
    outcome_id: str = "outcome-1",
) -> WorkbenchRagEvalAdjudicationPlanningInput:
    return WorkbenchRagEvalAdjudicationPlanningInput(
        run_id="run-1",
        project_id="project-1",
        question_id=question_id,
        question="Как оплатить?",
        evaluation_role=role,
        promotion_eligible=promotion_eligible,
        ambiguity_risk=risk,
        outcome_id=outcome_id,
        classification=classification,
        expected_runtime_entry_id="runtime-1",
        expected_fact_id="fact-1",
        expected_rank=None,
        expected_score=None,
        best_competitor_runtime_entry_id="runtime-2",
        best_competitor_fact_id="fact-2",
        best_competitor_score=0.71,
        score_margin=None,
        target_claim="Оплата доступна картой.",
        target_possible_questions=("Как оплатить заказ?",),
        target_exclusion_scope=None,
        target_evidence_block="Оплата картой.",
        retrieved=(
            WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot(
                rank=1,
                runtime_entry_id="runtime-2",
                fact_id="fact-2",
                claim="Доставка доступна курьером.",
                score=0.71,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (_input(classification=WorkbenchRagEvalRetrievalClassification.MISS), True),
        (
            _input(classification=WorkbenchRagEvalRetrievalClassification.CONFUSION),
            True,
        ),
        (
            _input(classification=WorkbenchRagEvalRetrievalClassification.PASS_WEAK),
            True,
        ),
        (
            _input(classification=WorkbenchRagEvalRetrievalClassification.PASS_STRONG),
            False,
        ),
        (_input(role=WorkbenchRagEvalQuestionRole.BASELINE), False),
        (
            _input(role=WorkbenchRagEvalQuestionRole.HOLDOUT, promotion_eligible=False),
            False,
        ),
        (_input(risk=WorkbenchRagEvalQuestionAmbiguityRisk.MEDIUM), False),
        (_input(risk=WorkbenchRagEvalQuestionAmbiguityRisk.HIGH), False),
        (_input(promotion_eligible=False), False),
    ],
)
def test_adjudication_eligibility_matrix(
    item: WorkbenchRagEvalAdjudicationPlanningInput,
    expected: bool,
) -> None:
    assert (
        WorkbenchRagEvalAdjudicationEligibilityPolicy().is_eligible(
            evaluation_role=item.evaluation_role,
            promotion_eligible=item.promotion_eligible,
            ambiguity_risk=item.ambiguity_risk,
            classification=item.classification,
        )
        is expected
    )


def test_planner_creates_stable_adjudication_work_items_with_immutable_snapshot() -> (
    None
):
    inputs = (
        _input(question_id="question-1", outcome_id="outcome-1"),
        _input(question_id="question-2", outcome_id="outcome-2"),
    )
    messages = {
        item.question_id: (
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": json.dumps({"question": item.question})},
        )
        for item in inputs
    }

    model_profile = model_budget_profile_for_ref("qwen/qwen3.6-27b")
    first = WorkbenchRagEvalAdjudicationWorkPlanner(
        adjudication_model_profile=model_profile,
    ).plan(
        inputs=inputs,
        provider_messages_by_question_id=messages,
    )
    second = WorkbenchRagEvalAdjudicationWorkPlanner(
        adjudication_model_profile=model_profile,
    ).plan(
        inputs=inputs,
        provider_messages_by_question_id=messages,
    )

    assert [plan.work_item_id for plan in first] == [
        plan.work_item_id for plan in second
    ]
    assert {plan.work_kind for plan in first} == {
        WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND
    }
    assert all(plan.payload["operation"] == "adjudication" for plan in first)
    assert all(
        plan.payload["prompt_version"] == ADJUDICATION_PROMPT_VERSION for plan in first
    )
    assert first[0].payload["target"] == {
        "runtime_entry_id": "runtime-1",
        "fact_id": "fact-1",
        "claim": "Оплата доступна картой.",
        "possible_questions": ["Как оплатить заказ?"],
        "exclusion_scope": None,
        "evidence_block": "Оплата картой.",
    }
    assert first[0].payload["retrieved"] == [
        {
            "rank": 1,
            "runtime_entry_id": "runtime-2",
            "fact_id": "fact-2",
            "claim": "Доставка доступна курьером.",
            "score": 0.71,
        }
    ]


@pytest.mark.parametrize("verdict", tuple(WorkbenchRagEvalAdjudicationVerdict))
def test_validation_accepts_all_known_verdicts(
    verdict: WorkbenchRagEvalAdjudicationVerdict,
) -> None:
    result = WorkbenchRagEvalAdjudicationOutputValidationPolicy().validate(
        raw_text=json.dumps(
            {
                "contract_version": WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION,
                "verdict": verdict.value,
                "promotion_recommended": verdict
                is WorkbenchRagEvalAdjudicationVerdict.VALID_TARGET_QUERY,
                "reason": "valid reason",
            }
        )
    )
    assert (
        result.outcome
        is WorkbenchRagEvalAdjudicationOutputValidationOutcome.VALID_ADJUDICATION
    )


@pytest.mark.parametrize(
    ("raw_text", "outcome"),
    [
        ("{", WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_JSON),
        ("[]", WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_ROOT),
        (
            json.dumps(
                {
                    "contract_version": "wrong",
                    "verdict": "valid_target_query",
                    "promotion_recommended": True,
                    "reason": "reason",
                }
            ),
            WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_CONTRACT_VERSION,
        ),
        (
            json.dumps(
                {
                    "contract_version": WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION,
                    "verdict": "unknown",
                    "promotion_recommended": False,
                    "reason": "reason",
                }
            ),
            WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_VERDICT,
        ),
        (
            json.dumps(
                {
                    "contract_version": WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION,
                    "verdict": "ambiguous",
                    "promotion_recommended": True,
                    "reason": "reason",
                }
            ),
            WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_PROMOTION_RECOMMENDATION,
        ),
        (
            json.dumps(
                {
                    "contract_version": WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION,
                    "verdict": "valid_target_query",
                    "promotion_recommended": True,
                    "reason": " ",
                }
            ),
            WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_REASON,
        ),
    ],
)
def test_validation_rejects_contract_errors(
    raw_text: str,
    outcome: WorkbenchRagEvalAdjudicationOutputValidationOutcome,
) -> None:
    assert (
        WorkbenchRagEvalAdjudicationOutputValidationPolicy()
        .validate(raw_text=raw_text)
        .outcome
        is outcome
    )


@pytest.mark.parametrize(
    ("summary", "complete", "expected"),
    [
        (
            _summary(ready_count=1, total_count=1),
            False,
            WorkbenchRagEvalAdjudicationProgressDecision.PREPARE_NEXT_BATCH_NOW,
        ),
        (
            _summary(
                retryable_failed_count=1,
                total_count=1,
                next_due_at=NOW + timedelta(minutes=5),
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
    ],
)
def test_reconcile_decision_matrix(
    summary: WorkItemProgressSummary,
    complete: bool,
    expected: WorkbenchRagEvalAdjudicationProgressDecision,
) -> None:
    assert (
        WorkbenchRagEvalAdjudicationProgressDecisionPolicy()
        .decide(summary=summary, now=NOW, adjudication_persistence_complete=complete)
        .decision
        is expected
    )


@dataclass(slots=True)
class FakeCommandLog:
    completed: list[WorkflowCommandId] = field(default_factory=list)
    appended: list[WorkflowCommand] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        self.appended.append(command)
        return command

    async def mark_command_completed(
        self, *, command_id: WorkflowCommandId, completed_at: datetime
    ) -> WorkflowCommand:
        del completed_at
        self.completed.append(command_id)
        return _reconcile_command()


@dataclass(slots=True)
class FakeSink:
    items: list[object] = field(default_factory=list)

    async def append_event(self, item: object) -> object:
        self.items.append(item)
        return item

    async def append_entry(self, item: object) -> object:
        self.items.append(item)
        return item

    async def save_snapshot(self, item: object) -> object:
        self.items.append(item)
        return item


def _reconcile_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:reconcile-adjudication"),
        command_type=WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS.value,
        workflow_run_id="run-1",
        idempotency_key=WorkflowIdempotencyKey("reconcile-adjudication"),
        payload={
            "workflow_run_id": "run-1",
            "rag_eval_run_id": "run-1",
            "project_id": "project-1",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_reconcile_drained_creates_candidates_and_enters_promotion_review() -> (
    None
):
    repo = SimpleNamespace(
        create_promotion_candidates_from_adjudications=AsyncMock(
            return_value=(
                WorkbenchRagEvalAdjudication(
                    adjudication_id="adj-1",
                    run_id="run-1",
                    project_id="project-1",
                    question_id="question-1",
                    outcome_id="outcome-1",
                    expected_runtime_entry_id="runtime-1",
                    expected_fact_id="fact-1",
                    verdict=WorkbenchRagEvalAdjudicationVerdict.VALID_TARGET_QUERY,
                    promotion_recommended=True,
                    reason="reason",
                    contract_version=WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION,
                    model_ref="qwen/qwen3.6-27b",
                    account_ref="groq_org_primary",
                    slot_index=0,
                    attempt_id="attempt-1",
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
        ),
        transition_run_progress=AsyncMock(),
    )
    uow = SimpleNamespace(
        command_log=FakeCommandLog(),
        outbox=FakeSink(),
        progress_snapshots=FakeSink(),
        timeline=FakeSink(),
    )

    await HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler().execute(
        HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand(
            _reconcile_command()
        ),
        work_item_progress_read_repository=SimpleNamespace(
            summarize_by_work_kind_and_workflow=AsyncMock(
                return_value=_summary(completed_count=1, total_count=1)
            )
        ),
        adjudication_coverage_repository=SimpleNamespace(
            has_adjudications_for_all_eligible_questions=AsyncMock(return_value=True)
        ),
        rag_eval_repository=repo,
        workflow_unit_of_work=uow,
    )

    repo.create_promotion_candidates_from_adjudications.assert_awaited_once()
    assert repo.transition_run_progress.await_count == 0
    assert any(
        getattr(event, "event_type", None) == "RagEvalPromotionCandidatesReady"
        for event in uow.outbox.items
    )


@pytest.mark.asyncio
async def test_reconcile_terminal_failure_blocks_without_candidates() -> None:
    repo = SimpleNamespace(
        create_promotion_candidates_from_adjudications=AsyncMock(return_value=()),
        transition_run_progress=AsyncMock(),
    )
    uow = SimpleNamespace(
        command_log=FakeCommandLog(),
        outbox=FakeSink(),
        progress_snapshots=FakeSink(),
        timeline=FakeSink(),
    )

    await HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler().execute(
        HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand(
            _reconcile_command()
        ),
        work_item_progress_read_repository=SimpleNamespace(
            summarize_by_work_kind_and_workflow=AsyncMock(
                return_value=_summary(terminal_failed_count=1, total_count=1)
            )
        ),
        adjudication_coverage_repository=SimpleNamespace(
            has_adjudications_for_all_eligible_questions=AsyncMock(return_value=False)
        ),
        rag_eval_repository=repo,
        workflow_unit_of_work=uow,
    )

    repo.create_promotion_candidates_from_adjudications.assert_not_awaited()
    transition = repo.transition_run_progress.await_args.kwargs
    assert transition["status"] is WorkbenchRagEvalRunStatus.BLOCKED
    assert transition["current_phase"] is WorkbenchRagEvalCurrentPhase.BLOCKED
