from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
    WorkItemProgressSummary,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_progress import (
    DraftClaimCompactionProgressSummary,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.application.ports.command_log_repository_port import (
    CommandLogRepositoryPort,
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


class DraftClaimCompactionProgressDecision(StrEnum):
    ACTIVE = "ACTIVE"
    PREPARE_NEXT_BATCH_NOW = "PREPARE_NEXT_BATCH_NOW"
    PREPARE_NEXT_BATCH_LATER = "PREPARE_NEXT_BATCH_LATER"
    WAITING_USER_MODEL_CHOICE = "WAITING_USER_MODEL_CHOICE"
    ALL_GROUPS_COMPACTED = "ALL_GROUPS_COMPACTED"
    COMPACTION_PROGRESS_BLOCKED = "COMPACTION_PROGRESS_BLOCKED"


DRAFT_CLAIM_COMPACTION_WORK_KIND = "knowledge_workbench.draft_claim_compaction"
DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF = "openai/gpt-oss-120b"
DRAFT_CLAIM_COMPACTION_WORKER_REF = (
    "knowledge-workbench-draft-claim-compaction-dispatch"
)
PENDING_COMPACTION_CONTINUATION_COMMAND_TYPES = (
    KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value,
    KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value,
    KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT.value,
    KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS.value,
)
PENDING_CURATION_OPEN_COMMAND_TYPES = (
    KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE.value,
)


@dataclass(frozen=True, slots=True)
class HandleReconcileDraftClaimCompactionProgressCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleReconcileDraftClaimCompactionProgressResult:
    workflow_run_id: str
    decision: str
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId


class HandleReconcileDraftClaimCompactionProgressCommandHandler:
    async def execute(
        self,
        command: HandleReconcileDraftClaimCompactionProgressCommand,
        *,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        compaction_reduction_state_repository: (
            DraftClaimCompactionReductionStateRepositoryPort
        ),
        work_item_progress_read_repository: WorkItemProgressReadRepositoryPort,
        command_log_repository: CommandLogRepositoryPort | None = None,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> HandleReconcileDraftClaimCompactionProgressResult:
        workflow_command = command.workflow_command
        _validate_workflow_command(workflow_command)

        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")

        occurred_at = workflow_command.updated_at
        command_log_read_repository = (
            workflow_unit_of_work.command_log
            if command_log_repository is None
            else command_log_repository
        )
        reduction_summary = (
            await compaction_reduction_state_repository.summarize_compaction_progress(
                workflow_run_id=workflow_run_id,
            )
        )
        execution_summary = (
            await work_item_progress_read_repository.summarize_by_work_kind_and_workflow(
                workflow_run_id=workflow_run_id,
                work_kind=WorkKind(DRAFT_CLAIM_COMPACTION_WORK_KIND),
                now=occurred_at,
            )
        )
        has_pending_compaction_continuation = (
            await command_log_read_repository.has_pending_commands(
                workflow_run_id=workflow_run_id,
                command_types=PENDING_COMPACTION_CONTINUATION_COMMAND_TYPES,
                excluding_command_id=workflow_command.command_id,
            )
        )
        has_pending_curation_open = (
            await command_log_read_repository.has_pending_commands(
                workflow_run_id=workflow_run_id,
                command_types=PENDING_CURATION_OPEN_COMMAND_TYPES,
                excluding_command_id=workflow_command.command_id,
            )
        )
        decision = _decide(
            reduction_summary,
            execution_summary,
            has_pending_compaction_continuation=has_pending_compaction_continuation,
            has_pending_curation_open=has_pending_curation_open,
        )

        next_command = _next_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            reduction_summary=reduction_summary,
            execution_summary=execution_summary,
            decision=decision,
            occurred_at=occurred_at,
        )
        appended_next_command_count = 0
        if next_command is not None:
            await workflow_unit_of_work.command_log.append_pending_command(next_command)
            appended_next_command_count = 1

        progress_event = _progress_reconciled_event(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            reduction_summary=reduction_summary,
            execution_summary=execution_summary,
            decision=decision,
            occurred_at=occurred_at,
            next_command=next_command,
        )
        persisted_progress_event = await workflow_unit_of_work.outbox.append_event(
            progress_event
        )
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(persisted_progress_event)
        appended_event_count = 1

        if decision is DraftClaimCompactionProgressDecision.ALL_GROUPS_COMPACTED:
            all_groups_compacted_event = _all_groups_compacted_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
                occurred_at=occurred_at,
                next_command=next_command,
            )
            persisted_all_groups_compacted_event = (
                await workflow_unit_of_work.outbox.append_event(
                    all_groups_compacted_event
                )
            )
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(
                    persisted_all_groups_compacted_event
                )
            appended_event_count += 1
        elif decision is DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE:
            waiting_user_choice_event = _waiting_user_choice_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
                occurred_at=occurred_at,
            )
            persisted_waiting_user_choice_event = (
                await workflow_unit_of_work.outbox.append_event(
                    waiting_user_choice_event
                )
            )
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(
                    persisted_waiting_user_choice_event
                )
            appended_event_count += 1
        elif decision is DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED:
            blocked_event = _progress_blocked_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
                occurred_at=occurred_at,
            )
            persisted_blocked_event = await workflow_unit_of_work.outbox.append_event(
                blocked_event
            )
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(persisted_blocked_event)
            appended_event_count += 1

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            reduction_summary=reduction_summary,
            execution_summary=execution_summary,
            decision=decision,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
                decision=decision,
                next_command=next_command,
                occurred_at=occurred_at,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return HandleReconcileDraftClaimCompactionProgressResult(
            workflow_run_id=workflow_run_id,
            decision=decision.value,
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS.value
    ):
        raise ValueError(
            "workflow_command command_type must be ReconcileDraftClaimCompactionProgress"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _decide(
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
    *,
    has_pending_compaction_continuation: bool = False,
    has_pending_curation_open: bool = False,
) -> DraftClaimCompactionProgressDecision:
    if reduction_summary.has_waiting_user_model_choice:
        return DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE
    if execution_summary.terminal_failed_count > 0:
        return DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED
    if execution_summary.due_waiting_count > 0:
        if has_pending_compaction_continuation:
            return DraftClaimCompactionProgressDecision.ACTIVE
        return DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_NOW
    if _has_future_waiting_work(execution_summary):
        if has_pending_compaction_continuation:
            return DraftClaimCompactionProgressDecision.ACTIVE
        return DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_LATER
    if execution_summary.leased_count > 0:
        return DraftClaimCompactionProgressDecision.ACTIVE
    if execution_summary.user_action_required_count > 0:
        return DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED
    if execution_summary.deferred_count > 0:
        return DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED
    if reduction_summary.all_groups_done:
        if has_pending_curation_open:
            return DraftClaimCompactionProgressDecision.ACTIVE
        if _has_clean_terminal_coverage(execution_summary):
            return DraftClaimCompactionProgressDecision.ALL_GROUPS_COMPACTED
        if has_pending_compaction_continuation:
            return DraftClaimCompactionProgressDecision.ACTIVE
        return DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED
    if has_pending_compaction_continuation:
        return DraftClaimCompactionProgressDecision.ACTIVE
    return DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED


def _next_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
    decision: DraftClaimCompactionProgressDecision,
    occurred_at: datetime,
) -> WorkflowCommand | None:
    del reduction_summary
    if decision is DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_NOW:
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            scheduled_work_item_count=execution_summary.due_waiting_count,
            run_after=occurred_at,
            occurred_at=occurred_at,
            suffix="now",
        )

    if decision is DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_LATER:
        if execution_summary.next_due_at is None:
            raise ValueError("next_due_at is required for delayed compaction prepare")
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            scheduled_work_item_count=_future_waiting_count(execution_summary),
            run_after=execution_summary.next_due_at,
            occurred_at=occurred_at,
            suffix=f"later:{execution_summary.next_due_at.isoformat()}",
        )

    if decision is not DraftClaimCompactionProgressDecision.ALL_GROUPS_COMPACTED:
        return None

    idempotency_key = f"draft-claim-curation-open:{workflow_run_id}"
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={
            "workflow_run_id": workflow_run_id,
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _prepare_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    scheduled_work_item_count: int,
    run_after: datetime,
    occurred_at: datetime,
    suffix: str,
) -> WorkflowCommand:
    causation_scope = _command_causation_scope(workflow_command)
    idempotency_key = (
        "draft-claim-compaction-dispatch:"
        f"{workflow_run_id}:reconcile:{suffix}:{causation_scope}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={
            "workflow_run_id": workflow_run_id,
            "work_kind": DRAFT_CLAIM_COMPACTION_WORK_KIND,
            "scheduled_work_item_count": scheduled_work_item_count,
            "active_model_ref": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
            "worker_ref": DRAFT_CLAIM_COMPACTION_WORKER_REF,
            "caused_by_command_id": workflow_command.command_id.value,
            "llm_dispatch_preparation": {
                "active_model_ref": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
                "requested_items": scheduled_work_item_count,
                "worker_ref": DRAFT_CLAIM_COMPACTION_WORKER_REF,
            },
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=run_after,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _command_causation_scope(workflow_command: WorkflowCommand) -> str:
    return hashlib.sha256(
        workflow_command.command_id.value.encode("utf-8"),
    ).hexdigest()[:12]


def _future_waiting_count(summary: WorkItemProgressSummary) -> int:
    future_retryable_count = (
        summary.retryable_failed_count - summary.due_retryable_failed_count
    )
    future_deferred_count = summary.deferred_count - summary.due_deferred_count
    if future_retryable_count < 0:
        raise ValueError("future retryable work count cannot be negative")
    if future_deferred_count < 0:
        raise ValueError("future deferred work count cannot be negative")
    future_waiting_count = future_retryable_count + future_deferred_count
    if future_waiting_count <= 0:
        raise ValueError("future waiting work count must be positive")
    if summary.next_due_at is None:
        raise ValueError("next_due_at is required for future waiting work")
    return future_waiting_count


def _has_future_waiting_work(summary: WorkItemProgressSummary) -> bool:
    future_retryable_count = (
        summary.retryable_failed_count - summary.due_retryable_failed_count
    )
    future_deferred_count = summary.deferred_count - summary.due_deferred_count
    return future_retryable_count + future_deferred_count > 0


def _has_clean_terminal_coverage(summary: WorkItemProgressSummary) -> bool:
    if summary.total_count == 0:
        return True
    return summary.terminal_coverage_count >= summary.total_count


def _progress_reconciled_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
    decision: DraftClaimCompactionProgressDecision,
    occurred_at: datetime,
    next_command: WorkflowCommand | None,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value}:"
            f"{workflow_command.command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "decision": decision.value,
            "summary": _summary_payload(
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
            ),
            "next_command_type": next_command.command_type if next_command else None,
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


def _all_groups_compacted_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
    occurred_at: datetime,
    next_command: WorkflowCommand | None,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ALL_GROUPS_COMPACTED.value}:"
            f"{workflow_command.command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ALL_GROUPS_COMPACTED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "summary": _summary_payload(
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
            ),
            "next_command_type": next_command.command_type if next_command else None,
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


def _waiting_user_choice_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
    occurred_at: datetime,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value}:"
            f"{workflow_command.command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "summary": _summary_payload(
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
            ),
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


def _progress_blocked_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
    occurred_at: datetime,
) -> WorkflowEvent:
    reason = _blocked_reason(
        reduction_summary=reduction_summary,
        execution_summary=execution_summary,
    )
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED.value}:"
            f"{workflow_command.command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "reason": reason,
            "group_counters": _group_counters_payload(reduction_summary),
            "execution_counters": _execution_counters_payload(execution_summary),
            "next_due_at": execution_summary.next_due_at.isoformat()
            if execution_summary.next_due_at is not None
            else None,
            "summary": _summary_payload(
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
            ),
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


def _blocked_reason(
    *,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
) -> str:
    if execution_summary.terminal_failed_count > 0:
        return "terminal_execution_failure"
    if execution_summary.user_action_required_count > 0:
        return "unexplained_user_action_required_work"
    if execution_summary.deferred_count > 0:
        return "unexplained_deferred_work"
    if not reduction_summary.all_groups_done:
        return "incomplete_groups_without_continuation"
    return "unclean_terminal_coverage"


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
    decision: DraftClaimCompactionProgressDecision,
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    for key, value in _summary_payload(
        reduction_summary=reduction_summary,
        execution_summary=execution_summary,
    ).items():
        if isinstance(value, int):
            domain_counters[f"draft_claim_compaction_{key}"] = value

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
            workflow_status=(
                "BLOCKED"
                if decision
                in {
                    DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE,
                    DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED,
                }
                else "RUNNING"
            ),
            total_work_items=execution_summary.total_count,
            scheduled_work_items=execution_summary.total_count,
            running_work_items=execution_summary.leased_count,
            completed_work_items=execution_summary.completed_count,
            deferred_work_items=execution_summary.deferred_count,
            retryable_failed_work_items=execution_summary.retryable_failed_count,
            terminal_failed_work_items=execution_summary.terminal_failed_count,
            blocked_work_items=(
                reduction_summary.waiting_user_model_choice_group_count
                if decision
                is DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE
                else execution_summary.user_action_required_count
                + execution_summary.terminal_failed_count
            ),
            domain_counters=domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=(
                occurred_at
                if decision
                is DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED
                else existing.completed_at if existing is not None else None
            ),
        )
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
    decision: DraftClaimCompactionProgressDecision,
    next_command: WorkflowCommand | None,
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            f"DraftClaimCompactionProgressReconciled:{workflow_command.command_id.value}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value
        ),
        phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
        severity=(
            WorkflowTimelineSeverity.WARNING
            if decision
            in {
                DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE,
                DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED,
            }
            else WorkflowTimelineSeverity.INFO
        ),
        message=_timeline_message(decision),
        payload_summary={
            "workflow_run_id": workflow_run_id,
            "decision": decision.value,
            "summary": _summary_payload(
                reduction_summary=reduction_summary,
                execution_summary=execution_summary,
            ),
            "next_command_type": next_command.command_type if next_command else None,
        },
        occurred_at=occurred_at,
        source_ref=workflow_command.command_type,
    )


def _timeline_message(decision: DraftClaimCompactionProgressDecision) -> str:
    if decision is DraftClaimCompactionProgressDecision.ALL_GROUPS_COMPACTED:
        return "Draft claim compaction all groups compacted"
    if decision is DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE:
        return "Draft claim compaction waiting for user model choice"
    if decision is DraftClaimCompactionProgressDecision.COMPACTION_PROGRESS_BLOCKED:
        return "Draft claim compaction blocked"
    return "Draft claim compaction progress reconciled"


def _summary_payload(
    *,
    reduction_summary: DraftClaimCompactionProgressSummary,
    execution_summary: WorkItemProgressSummary,
) -> dict[str, object]:
    payload = reduction_summary.to_payload()
    payload.update(_execution_counters_payload(execution_summary))
    return payload


def _group_counters_payload(
    summary: DraftClaimCompactionProgressSummary,
) -> dict[str, object]:
    return {
        "group_count": summary.group_count,
        "done_group_count": summary.done_group_count,
        "active_group_count": summary.active_group_count,
    }


def _execution_counters_payload(
    summary: WorkItemProgressSummary,
) -> dict[str, object]:
    payload = summary.to_payload()
    payload["due_waiting_count"] = summary.due_waiting_count
    payload["terminal_coverage_count"] = summary.terminal_coverage_count
    payload["has_future_waiting_work"] = _has_future_waiting_work(summary)
    return payload


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value
