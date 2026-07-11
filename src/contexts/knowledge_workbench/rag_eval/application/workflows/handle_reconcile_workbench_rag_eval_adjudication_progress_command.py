from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
    WorkItemProgressSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
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


class WorkbenchRagEvalAdjudicationProgressDecision(StrEnum):
    PREPARE_NEXT_BATCH_NOW = "PREPARE_NEXT_BATCH_NOW"
    PREPARE_NEXT_BATCH_LATER = "PREPARE_NEXT_BATCH_LATER"
    WAIT_FOR_ACTIVE_ATTEMPTS = "WAIT_FOR_ACTIVE_ATTEMPTS"
    ADJUDICATION_DRAINED = "ADJUDICATION_DRAINED"
    ADJUDICATION_BLOCKED = "ADJUDICATION_BLOCKED"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationProgressDecisionResult:
    decision: WorkbenchRagEvalAdjudicationProgressDecision
    next_due_at: datetime | None = None


class WorkbenchRagEvalAdjudicationProgressDecisionPolicy:
    def decide(
        self,
        *,
        summary: WorkItemProgressSummary,
        now: datetime,
        adjudication_persistence_complete: bool,
        zero_eligible_fast_path: bool = False,
    ) -> WorkbenchRagEvalAdjudicationProgressDecisionResult:
        if summary.terminal_failed_count > 0:
            return WorkbenchRagEvalAdjudicationProgressDecisionResult(
                WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_BLOCKED
            )
        if summary.total_count == 0:
            return WorkbenchRagEvalAdjudicationProgressDecisionResult(
                WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_DRAINED
                if zero_eligible_fast_path
                else WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_BLOCKED
            )
        if summary.due_waiting_count > 0:
            return WorkbenchRagEvalAdjudicationProgressDecisionResult(
                WorkbenchRagEvalAdjudicationProgressDecision.PREPARE_NEXT_BATCH_NOW
            )
        if summary.has_future_waiting_work:
            if summary.next_due_at is None or summary.next_due_at <= now:
                raise ValueError("future waiting work requires future next_due_at")
            return WorkbenchRagEvalAdjudicationProgressDecisionResult(
                WorkbenchRagEvalAdjudicationProgressDecision.PREPARE_NEXT_BATCH_LATER,
                summary.next_due_at,
            )
        if summary.leased_count > 0:
            return WorkbenchRagEvalAdjudicationProgressDecisionResult(
                WorkbenchRagEvalAdjudicationProgressDecision.WAIT_FOR_ACTIVE_ATTEMPTS
            )
        if summary.completed_count == summary.total_count:
            return WorkbenchRagEvalAdjudicationProgressDecisionResult(
                WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_DRAINED
                if adjudication_persistence_complete
                else WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_BLOCKED
            )
        return WorkbenchRagEvalAdjudicationProgressDecisionResult(
            WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_BLOCKED
        )


class AdjudicationPersistenceCoveragePort(Protocol):
    async def has_adjudications_for_all_eligible_questions(
        self,
        *,
        run_id: str,
        project_id: str,
        pass_weak_enabled: bool,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleReconcileWorkbenchRagEvalAdjudicationProgressResult:
    decision: str
    promotion_candidate_count: int


class HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler:
    async def execute(
        self,
        command: HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand,
        *,
        work_item_progress_read_repository: WorkItemProgressReadRepositoryPort,
        adjudication_coverage_repository: AdjudicationPersistenceCoveragePort,
        rag_eval_repository: WorkbenchRagEvalRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleReconcileWorkbenchRagEvalAdjudicationProgressResult:
        current = command.workflow_command
        if (
            current.command_type
            != WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS.value
            or current.status is not WorkflowCommandStatus.PENDING
        ):
            raise ValueError("workflow command must be pending adjudication reconcile")
        run_id = _payload_text(
            current, "workflow_run_id", fallback=current.workflow_run_id
        )
        project_id = _payload_text(current, "project_id")
        now = current.updated_at
        summary = await work_item_progress_read_repository.summarize_by_work_kind_and_workflow(
            workflow_run_id=run_id,
            work_kind=WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
            now=now,
        )
        complete = await adjudication_coverage_repository.has_adjudications_for_all_eligible_questions(
            run_id=run_id,
            project_id=project_id,
            pass_weak_enabled=True,
        )
        decision = WorkbenchRagEvalAdjudicationProgressDecisionPolicy().decide(
            summary=summary,
            now=now,
            adjudication_persistence_complete=complete,
        )
        candidate_count = 0
        if (
            decision.decision
            is WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_DRAINED
        ):
            candidates = await rag_eval_repository.create_promotion_candidates_from_adjudications(
                run_id=run_id,
                project_id=project_id,
                created_at=now,
                pass_weak_enabled=True,
            )
            candidate_count = len(candidates)
        else:
            status, phase, blocked_reason = _run_transition(decision)
            await rag_eval_repository.transition_run_progress(
                run_id=run_id,
                project_id=project_id,
                status=status,
                current_phase=phase,
                progress=_progress(summary),
                updated_at=now,
                blocked_reason=blocked_reason,
                capacity_next_due_at=decision.next_due_at,
            )
        next_command = _next_command(current, decision, summary, now)
        if next_command is not None:
            await workflow_unit_of_work.command_log.append_pending_command(next_command)
        await workflow_unit_of_work.outbox.append_event(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{run_id}:adjudication-reconciled:{current.command_id.value}"
                ),
                event_type=WorkbenchRagEvalWorkflowEventType.ADJUDICATION_PROGRESS_RECONCILED.value,
                workflow_run_id=run_id,
                payload={
                    "workflow_run_id": run_id,
                    "decision": decision.decision.value,
                    "summary": summary.to_payload(),
                },
                occurred_at=now,
                causation_command_id=current.command_id,
            )
        )
        if (
            decision.decision
            is WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_DRAINED
        ):
            await workflow_unit_of_work.outbox.append_event(
                WorkflowEvent(
                    event_id=WorkflowEventId(
                        f"workflow-event:{run_id}:promotion-candidates-ready:{current.command_id.value}"
                    ),
                    event_type=WorkbenchRagEvalWorkflowEventType.PROMOTION_CANDIDATES_READY.value,
                    workflow_run_id=run_id,
                    payload={
                        "workflow_run_id": run_id,
                        "candidate_count": candidate_count,
                    },
                    occurred_at=now,
                    causation_command_id=current.command_id,
                )
            )
        phase_for_snapshot = _snapshot_phase(decision)
        await workflow_unit_of_work.progress_snapshots.save_snapshot(
            WorkflowProgressSnapshot(
                workflow_run_id=run_id,
                current_phase=phase_for_snapshot.value,
                workflow_status="BLOCKED"
                if phase_for_snapshot is WorkbenchRagEvalWorkflowPhase.BLOCKED
                else (
                    "PROMOTION_REVIEW"
                    if phase_for_snapshot
                    is WorkbenchRagEvalWorkflowPhase.PROMOTION_REVIEW
                    else "RUNNING"
                ),
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
                timeline_entry_id=f"timeline:{run_id}:adjudication-reconciled:{current.command_id.value}",
                workflow_run_id=run_id,
                event_type=WorkbenchRagEvalWorkflowEventType.ADJUDICATION_PROGRESS_RECONCILED.value,
                phase=phase_for_snapshot.value,
                severity=WorkflowTimelineSeverity.ERROR
                if phase_for_snapshot is WorkbenchRagEvalWorkflowPhase.BLOCKED
                else WorkflowTimelineSeverity.INFO,
                message=f"Adjudication reconcile: {decision.decision.value}",
                payload_summary=summary.to_payload(),
                occurred_at=now,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=current.command_id,
            completed_at=now,
        )
        return HandleReconcileWorkbenchRagEvalAdjudicationProgressResult(
            decision.decision.value,
            candidate_count,
        )


def _next_command(
    current: WorkflowCommand,
    result: WorkbenchRagEvalAdjudicationProgressDecisionResult,
    summary: WorkItemProgressSummary,
    now: datetime,
) -> WorkflowCommand | None:
    if result.decision not in (
        WorkbenchRagEvalAdjudicationProgressDecision.PREPARE_NEXT_BATCH_NOW,
        WorkbenchRagEvalAdjudicationProgressDecision.PREPARE_NEXT_BATCH_LATER,
    ):
        return None
    command_type = (
        WorkbenchRagEvalWorkflowCommandType.PREPARE_ADJUDICATION_DISPATCH_BATCH
    )
    run_after = result.next_due_at or now
    key = f"rag-eval:{current.workflow_run_id}:{command_type.value}:{run_after.isoformat()}"
    payload = dict(current.payload)
    payload["scheduled_work_item_count"] = (
        summary.due_waiting_count
        or summary.retryable_failed_count
        or summary.total_count
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
    result: WorkbenchRagEvalAdjudicationProgressDecisionResult,
) -> tuple[WorkbenchRagEvalRunStatus, WorkbenchRagEvalCurrentPhase, str | None]:
    if (
        result.decision
        is WorkbenchRagEvalAdjudicationProgressDecision.PREPARE_NEXT_BATCH_LATER
    ):
        return (
            WorkbenchRagEvalRunStatus.WAITING_CAPACITY,
            WorkbenchRagEvalCurrentPhase.ADJUDICATION,
            None,
        )
    if (
        result.decision
        is WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_BLOCKED
    ):
        return (
            WorkbenchRagEvalRunStatus.BLOCKED,
            WorkbenchRagEvalCurrentPhase.BLOCKED,
            "adjudication_incomplete_or_terminal_failure",
        )
    return (
        WorkbenchRagEvalRunStatus.RUNNING,
        WorkbenchRagEvalCurrentPhase.ADJUDICATION,
        None,
    )


def _snapshot_phase(
    result: WorkbenchRagEvalAdjudicationProgressDecisionResult,
) -> WorkbenchRagEvalWorkflowPhase:
    if (
        result.decision
        is WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_BLOCKED
    ):
        return WorkbenchRagEvalWorkflowPhase.BLOCKED
    if (
        result.decision
        is WorkbenchRagEvalAdjudicationProgressDecision.ADJUDICATION_DRAINED
    ):
        return WorkbenchRagEvalWorkflowPhase.PROMOTION_REVIEW
    return WorkbenchRagEvalWorkflowPhase.ADJUDICATION


def _progress(summary: WorkItemProgressSummary) -> WorkbenchRagEvalRunProgress:
    return WorkbenchRagEvalRunProgress(
        adjudication_total=summary.total_count,
        adjudication_waiting=summary.ready_count
        + summary.deferred_count
        + summary.retryable_failed_count,
        adjudication_running=summary.leased_count,
        adjudication_completed=summary.completed_count,
        adjudication_failed=summary.terminal_failed_count,
    )


def _payload_text(
    current: WorkflowCommand,
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = current.payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payload.{key} must be non-empty")
    return value.strip()
