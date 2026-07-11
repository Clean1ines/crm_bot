from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from typing import Protocol

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionDetails,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
    WorkbenchRagEvalRetrievalOutcome,
    WorkbenchRagEvalRetrievalResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_retrieval_outcome_policy import (
    WorkbenchRagEvalRetrievalOutcomePolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
    WorkbenchRagEvalWorkflowEventType,
    WorkbenchRagEvalWorkflowPhase,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


class PublishedWorkbenchSearchPort(Protocol):
    async def execute(
        self, *, project_id: str, query_text: str, limit: int = 10
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]: ...


@dataclass(frozen=True, slots=True)
class HandleRunWorkbenchRagEvalRetrievalEvaluationCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleRunWorkbenchRagEvalRetrievalEvaluationResult:
    evaluated_question_count: int
    saved_result_count: int
    appended_command_count: int


class HandleRunWorkbenchRagEvalRetrievalEvaluationCommandHandler:
    async def execute(
        self,
        command: HandleRunWorkbenchRagEvalRetrievalEvaluationCommand,
        *,
        search_published_workbench_runtime: PublishedWorkbenchSearchPort,
        rag_eval_repository: WorkbenchRagEvalRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleRunWorkbenchRagEvalRetrievalEvaluationResult:
        current = command.workflow_command
        if (
            current.command_type
            != WorkbenchRagEvalWorkflowCommandType.RUN_RETRIEVAL_EVALUATION.value
            or current.status is not WorkflowCommandStatus.PENDING
        ):
            raise ValueError("workflow command must be pending retrieval evaluation")
        run_id = _required_text(current.payload, "workflow_run_id")
        rag_eval_run_id = _required_text(current.payload, "rag_eval_run_id")
        project_id = _required_text(current.payload, "project_id")
        if run_id != current.workflow_run_id or rag_eval_run_id != run_id:
            raise ValueError("workflow and RAG Eval run ids must match")
        top_k = _required_int(current.payload, "top_k", default=5)
        if top_k < 5:
            raise ValueError("top_k must be at least 5")
        await rag_eval_repository.materialize_baseline_questions(
            run_id=rag_eval_run_id,
            project_id=project_id,
            created_at=current.updated_at,
        )
        questions = await rag_eval_repository.list_run_questions(
            project_id=project_id, run_id=rag_eval_run_id
        )
        if not questions:
            raise ValueError("retrieval evaluation requires persisted questions")

        all_results: list[WorkbenchRagEvalRetrievalResult] = []
        outcomes: list[WorkbenchRagEvalRetrievalOutcome] = []
        now = current.updated_at
        for question in questions:
            retrieved = await search_published_workbench_runtime.execute(
                project_id=project_id,
                query_text=question.question,
                limit=top_k,
            )
            results = _diagnostic_results(question, retrieved, now)
            all_results.extend(results)
            outcomes.append(_outcome(question, retrieved, now))

        await rag_eval_repository.save_retrieval_results(results=tuple(all_results))
        await rag_eval_repository.save_retrieval_outcomes(outcomes=tuple(outcomes))
        await rag_eval_repository.mark_questions_evaluated(
            run_id=rag_eval_run_id,
            question_ids=tuple(question.question_id for question in questions),
            evaluated_at=now,
        )
        counts = _classification_counts(outcomes)
        await rag_eval_repository.complete_initial_retrieval_evaluation(
            run_id=rag_eval_run_id,
            project_id=project_id,
            total_questions=len(questions),
            classification_counts=counts,
            updated_at=now,
        )
        next_command = _adjudication_command(current, top_k, now)
        await workflow_unit_of_work.command_log.append_pending_command(next_command)
        event_payload = {
            "workflow_run_id": run_id,
            "rag_eval_run_id": rag_eval_run_id,
            "project_id": project_id,
            "phase": WorkbenchRagEvalWorkflowPhase.RETRIEVAL_EVALUATION.value,
            "evaluated_question_count": len(questions),
            "saved_result_count": len(all_results),
            "classification_counts": counts,
        }
        await workflow_unit_of_work.outbox.append_event(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{run_id}:retrieval-completed:{current.command_id.value}"
                ),
                event_type=WorkbenchRagEvalWorkflowEventType.RETRIEVAL_EVALUATION_COMPLETED.value,
                workflow_run_id=run_id,
                payload=event_payload,
                occurred_at=now,
                causation_command_id=current.command_id,
            )
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=f"timeline:{run_id}:retrieval-completed:{current.command_id.value}",
                workflow_run_id=run_id,
                event_type=WorkbenchRagEvalWorkflowEventType.RETRIEVAL_EVALUATION_COMPLETED.value,
                phase=WorkbenchRagEvalWorkflowPhase.RETRIEVAL_EVALUATION.value,
                severity=WorkflowTimelineSeverity.INFO,
                message="RAG Eval retrieval evaluation completed",
                payload_summary=event_payload,
                occurred_at=now,
            )
        )
        await workflow_unit_of_work.progress_snapshots.save_snapshot(
            WorkflowProgressSnapshot(
                workflow_run_id=run_id,
                current_phase=WorkbenchRagEvalWorkflowPhase.ADJUDICATION_SCHEDULING.value,
                workflow_status="RUNNING",
                total_work_items=len(questions),
                scheduled_work_items=len(questions),
                running_work_items=0,
                completed_work_items=len(questions),
                deferred_work_items=0,
                retryable_failed_work_items=0,
                terminal_failed_work_items=0,
                blocked_work_items=0,
                updated_at=now,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=current.command_id, completed_at=now
        )
        return HandleRunWorkbenchRagEvalRetrievalEvaluationResult(
            len(questions), len(all_results), 1
        )


def _diagnostic_results(
    question: WorkbenchRagEvalQuestionDetails,
    retrieved: tuple[PublishedWorkbenchRetrievalResult, ...],
    now: datetime,
) -> tuple[WorkbenchRagEvalRetrievalResult, ...]:
    return tuple(
        WorkbenchRagEvalRetrievalResult(
            result_id=_stable_id(
                "result",
                question.run_id,
                question.question_id,
                "initial",
                item.runtime_entry_id,
                str(item.rank),
            ),
            run_id=question.run_id,
            question_id=question.question_id,
            project_id=question.project_id,
            expected_runtime_entry_id=question.expected_runtime_entry_id,
            matched_runtime_entry_id=item.runtime_entry_id,
            matched_fact_id=item.fact_id,
            rank=item.rank,
            score=item.score,
            top1_hit=item.runtime_entry_id == question.expected_runtime_entry_id
            and item.rank <= 1,
            top3_hit=item.runtime_entry_id == question.expected_runtime_entry_id
            and item.rank <= 3,
            top5_hit=item.runtime_entry_id == question.expected_runtime_entry_id
            and item.rank <= 5,
            created_at=now,
        )
        for item in retrieved
    )


def _outcome(
    question: WorkbenchRagEvalQuestionDetails,
    retrieved: tuple[PublishedWorkbenchRetrievalResult, ...],
    now: datetime,
) -> WorkbenchRagEvalRetrievalOutcome:
    expected = next(
        (
            item
            for item in retrieved
            if item.runtime_entry_id == question.expected_runtime_entry_id
        ),
        None,
    )
    competitor = next(
        (
            item
            for item in retrieved
            if item.runtime_entry_id != question.expected_runtime_entry_id
        ),
        None,
    )
    outcome = WorkbenchRagEvalRetrievalOutcomePolicy().build(
        outcome_id=_stable_id(
            "outcome", question.run_id, question.question_id, "initial"
        ),
        run_id=question.run_id,
        question_id=question.question_id,
        project_id=question.project_id,
        evaluation_stage="initial",
        expected_runtime_entry_id=question.expected_runtime_entry_id,
        expected_fact_id=question.expected_fact_id,
        expected_rank=expected.rank if expected else None,
        expected_score=expected.score if expected else None,
        best_competitor_runtime_entry_id=competitor.runtime_entry_id
        if competitor
        else None,
        best_competitor_fact_id=competitor.fact_id if competitor else None,
        best_competitor_score=competitor.score if competitor else None,
        competitor_same_document=_competitor_ranks_above_expected(
            competitor=competitor,
            expected=expected,
        ),
        created_at=now,
    )
    if question.evaluation_role is WorkbenchRagEvalQuestionRole.BASELINE and (
        expected is None or expected.rank > 3
    ):
        return replace(
            outcome,
            classification=(
                WorkbenchRagEvalRetrievalClassification.EXISTING_ALIAS_RETRIEVAL_FAILURE
            ),
        )
    return outcome


def _classification_counts(
    outcomes: list[WorkbenchRagEvalRetrievalOutcome],
) -> dict[str, int]:
    return {
        classification.value: sum(
            outcome.classification is classification for outcome in outcomes
        )
        for classification in WorkbenchRagEvalRetrievalClassification
    }


def _competitor_ranks_above_expected(
    *,
    competitor: PublishedWorkbenchRetrievalResult | None,
    expected: PublishedWorkbenchRetrievalResult | None,
) -> bool:
    return bool(competitor and (expected is None or competitor.rank < expected.rank))


def _adjudication_command(
    current: WorkflowCommand, top_k: int, now: datetime
) -> WorkflowCommand:
    command_type = WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK
    key = f"rag-eval:{current.workflow_run_id}:{command_type.value}:initial"
    payload = dict(current.payload)
    payload["top_k"] = top_k
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{key}"),
        command_type=command_type.value,
        workflow_run_id=current.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=now,
        created_at=now,
        updated_at=now,
    )


def _stable_id(*parts: str) -> str:
    return sha256("\x1f".join(parts).encode()).hexdigest()


def _required_text(payload: object, key: str) -> str:
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be mapping")
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payload.{key} must be non-empty")
    return value.strip()


def _required_int(payload: object, key: str, *, default: int) -> int:
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be mapping")
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"payload.{key} must be int")
    return value
