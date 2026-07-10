from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
    WorkItemProgressSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
    WorkbenchRagEvalWorkflowEventType,
    WorkbenchRagEvalWorkflowPhase,
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


class WorkbenchRagEvalQuestionGenerationProgressDecision(StrEnum):
    PREPARE_NEXT_BATCH_NOW = "PREPARE_NEXT_BATCH_NOW"
    PREPARE_NEXT_BATCH_LATER = "PREPARE_NEXT_BATCH_LATER"
    WAIT_FOR_ACTIVE_ATTEMPTS = "WAIT_FOR_ACTIVE_ATTEMPTS"
    QUESTION_GENERATION_DRAINED = "QUESTION_GENERATION_DRAINED"
    QUESTION_GENERATION_BLOCKED = "QUESTION_GENERATION_BLOCKED"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerationProgressDecisionResult:
    decision: WorkbenchRagEvalQuestionGenerationProgressDecision
    next_due_at: datetime | None = None


class WorkbenchRagEvalQuestionGenerationProgressDecisionPolicy:
    def decide(
        self,
        *,
        summary: WorkItemProgressSummary,
        now: datetime,
        domain_persistence_complete: bool,
    ) -> WorkbenchRagEvalQuestionGenerationProgressDecisionResult:
        if summary.terminal_failed_count > 0 or summary.total_count == 0:
            decision = WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_BLOCKED
        elif summary.due_waiting_count > 0:
            decision = WorkbenchRagEvalQuestionGenerationProgressDecision.PREPARE_NEXT_BATCH_NOW
        elif summary.has_future_waiting_work:
            if summary.next_due_at is None or summary.next_due_at <= now:
                raise ValueError("future waiting work requires future next_due_at")
            return WorkbenchRagEvalQuestionGenerationProgressDecisionResult(
                WorkbenchRagEvalQuestionGenerationProgressDecision.PREPARE_NEXT_BATCH_LATER,
                summary.next_due_at,
            )
        elif summary.leased_count > 0:
            decision = WorkbenchRagEvalQuestionGenerationProgressDecision.WAIT_FOR_ACTIVE_ATTEMPTS
        elif (
            summary.completed_count == summary.total_count
            and domain_persistence_complete
        ):
            decision = WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_DRAINED
        else:
            decision = WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_BLOCKED
        return WorkbenchRagEvalQuestionGenerationProgressDecisionResult(decision)


class QuestionGenerationPersistenceCoveragePort(Protocol):
    async def has_complete_question_sets(
        self,
        *,
        rag_eval_run_id: str,
        expected_entry_count: int,
        questions_per_entry: int,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleReconcileWorkbenchRagEvalQuestionGenerationProgressResult:
    decision: str
    appended_next_command_count: int


class HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler:
    async def execute(
        self,
        command: HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand,
        *,
        work_item_progress_read_repository: WorkItemProgressReadRepositoryPort,
        question_coverage_repository: QuestionGenerationPersistenceCoveragePort,
        rag_eval_repository: WorkbenchRagEvalRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleReconcileWorkbenchRagEvalQuestionGenerationProgressResult:
        current = command.workflow_command
        if (
            current.command_type
            != WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value
            or current.status is not WorkflowCommandStatus.PENDING
        ):
            raise ValueError("workflow command must be pending qgen reconcile")
        run_id = _text(current.payload, "workflow_run_id", current.workflow_run_id)
        if run_id != current.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")
        rag_eval_run_id = _text(current.payload, "rag_eval_run_id", "")
        project_id = _text(current.payload, "project_id", "")
        now = current.updated_at
        summary = await work_item_progress_read_repository.summarize_by_work_kind_and_workflow(
            workflow_run_id=run_id,
            work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
            now=now,
        )
        complete = await question_coverage_repository.has_complete_question_sets(
            rag_eval_run_id=run_id,
            expected_entry_count=summary.total_count,
            questions_per_entry=10,
        )
        result = WorkbenchRagEvalQuestionGenerationProgressDecisionPolicy().decide(
            summary=summary, now=now, domain_persistence_complete=complete
        )
        run_status, run_phase, blocked_reason = _run_transition(result)
        await rag_eval_repository.transition_run_progress(
            run_id=rag_eval_run_id,
            project_id=project_id,
            status=run_status,
            current_phase=run_phase,
            progress=WorkbenchRagEvalRunProgress(
                selected_entries=summary.total_count,
                scheduled_generation_items=summary.total_count,
                waiting=summary.ready_count
                + summary.deferred_count
                + summary.retryable_failed_count,
                running=summary.leased_count,
                completed=summary.completed_count,
                failed=summary.terminal_failed_count,
                generated_question_sets=summary.completed_count if complete else 0,
            ),
            updated_at=now,
            blocked_reason=blocked_reason,
            capacity_next_due_at=result.next_due_at,
        )
        next_command = _next_command(current, result, summary, now)
        if next_command is not None:
            await workflow_unit_of_work.command_log.append_pending_command(next_command)
        event = WorkflowEvent(
            event_id=WorkflowEventId(
                f"workflow-event:{run_id}:qgen-reconciled:{current.command_id.value}"
            ),
            event_type=WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_PROGRESS_RECONCILED.value,
            workflow_run_id=run_id,
            payload={
                "workflow_run_id": run_id,
                "decision": result.decision.value,
                "summary": summary.to_payload(),
            },
            occurred_at=now,
            causation_command_id=current.command_id,
        )
        await workflow_unit_of_work.outbox.append_event(event)
        if (
            result.decision
            is WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_DRAINED
        ):
            await workflow_unit_of_work.outbox.append_event(
                WorkflowEvent(
                    event_id=WorkflowEventId(
                        f"workflow-event:{run_id}:qgen-completed:{current.command_id.value}"
                    ),
                    event_type=WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_COMPLETED.value,
                    workflow_run_id=run_id,
                    payload={"workflow_run_id": run_id},
                    occurred_at=now,
                    causation_command_id=current.command_id,
                )
            )
        phase = (
            WorkbenchRagEvalWorkflowPhase.BLOCKED
            if result.decision
            is WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_BLOCKED
            else (
                WorkbenchRagEvalWorkflowPhase.RETRIEVAL_EVALUATION
                if result.decision
                is WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_DRAINED
                else WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION
            )
        )
        status = (
            "BLOCKED" if phase is WorkbenchRagEvalWorkflowPhase.BLOCKED else "RUNNING"
        )
        await workflow_unit_of_work.progress_snapshots.save_snapshot(
            WorkflowProgressSnapshot(
                workflow_run_id=run_id,
                current_phase=phase.value,
                workflow_status=status,
                total_work_items=summary.total_count,
                scheduled_work_items=summary.total_count,
                running_work_items=summary.leased_count,
                completed_work_items=summary.completed_count,
                deferred_work_items=summary.deferred_count,
                retryable_failed_work_items=summary.retryable_failed_count,
                terminal_failed_work_items=summary.terminal_failed_count,
                blocked_work_items=summary.terminal_failed_count,
                updated_at=now,
            )
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=f"timeline:{run_id}:qgen-reconciled:{current.command_id.value}",
                workflow_run_id=run_id,
                event_type=WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_PROGRESS_RECONCILED.value,
                phase=phase.value,
                severity=WorkflowTimelineSeverity.ERROR
                if status == "BLOCKED"
                else WorkflowTimelineSeverity.INFO,
                message=f"Question generation reconcile: {result.decision.value}",
                payload_summary=summary.to_payload(),
                occurred_at=now,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=current.command_id, completed_at=now
        )
        return HandleReconcileWorkbenchRagEvalQuestionGenerationProgressResult(
            result.decision.value, int(next_command is not None)
        )


def _next_command(
    current: WorkflowCommand,
    result: WorkbenchRagEvalQuestionGenerationProgressDecisionResult,
    summary: WorkItemProgressSummary,
    now: datetime,
) -> WorkflowCommand | None:
    if result.decision in (
        WorkbenchRagEvalQuestionGenerationProgressDecision.PREPARE_NEXT_BATCH_NOW,
        WorkbenchRagEvalQuestionGenerationProgressDecision.PREPARE_NEXT_BATCH_LATER,
    ):
        run_after = result.next_due_at or now
        command_type = WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH
        count = summary.due_waiting_count or summary.retryable_failed_count
    elif (
        result.decision
        is WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_DRAINED
    ):
        run_after, command_type, count = (
            now,
            WorkbenchRagEvalWorkflowCommandType.RUN_RETRIEVAL_EVALUATION,
            0,
        )
    else:
        return None
    key = f"rag-eval:{current.workflow_run_id}:{command_type.value}:{run_after.isoformat()}"
    payload = dict(current.payload)
    payload.update(
        {"workflow_run_id": current.workflow_run_id, "scheduled_work_item_count": count}
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{key}"),
        command_type=command_type.value,
        workflow_run_id=current.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=run_after,
        created_at=now,
        updated_at=now,
    )


def _run_transition(
    result: WorkbenchRagEvalQuestionGenerationProgressDecisionResult,
) -> tuple[WorkbenchRagEvalRunStatus, WorkbenchRagEvalCurrentPhase, str | None]:
    if (
        result.decision
        is WorkbenchRagEvalQuestionGenerationProgressDecision.PREPARE_NEXT_BATCH_LATER
    ):
        return (
            WorkbenchRagEvalRunStatus.WAITING_CAPACITY,
            WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION,
            None,
        )
    if (
        result.decision
        is WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_BLOCKED
    ):
        return (
            WorkbenchRagEvalRunStatus.BLOCKED,
            WorkbenchRagEvalCurrentPhase.BLOCKED,
            "question_generation_incomplete_or_terminal_failure",
        )
    if (
        result.decision
        is WorkbenchRagEvalQuestionGenerationProgressDecision.QUESTION_GENERATION_DRAINED
    ):
        return (
            WorkbenchRagEvalRunStatus.RUNNING,
            WorkbenchRagEvalCurrentPhase.RETRIEVAL_EVALUATION,
            None,
        )
    return (
        WorkbenchRagEvalRunStatus.RUNNING,
        WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION,
        None,
    )


def _text(payload: object, key: str, fallback: str) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty")
    return value
