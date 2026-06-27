from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.application.sagas.llm_dispatch_ownership_policy import (
    current_llm_dispatch_ownership_policy,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_progress import (
    DraftClaimCompactionProgressSummary,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
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


class DraftClaimCompactionProgressDecision(StrEnum):
    ACTIVE = "ACTIVE"
    PREPARE_NEXT_BATCH_NOW = "PREPARE_NEXT_BATCH_NOW"
    PREPARE_NEXT_BATCH_LATER = "PREPARE_NEXT_BATCH_LATER"
    WAITING_USER_MODEL_CHOICE = "WAITING_USER_MODEL_CHOICE"
    ALL_GROUPS_COMPACTED = "ALL_GROUPS_COMPACTED"


DRAFT_CLAIM_COMPACTION_WORK_KIND = "knowledge_workbench.draft_claim_compaction"
DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF = "openai/gpt-oss-120b"
DRAFT_CLAIM_COMPACTION_WORKER_REF = (
    "knowledge-workbench-draft-claim-compaction-dispatch"
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
        summary = (
            await compaction_reduction_state_repository.summarize_compaction_progress(
                workflow_run_id=workflow_run_id,
            )
        )
        decision = _decide(summary)

        next_command = _next_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            summary=summary,
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
            summary=summary,
            decision=decision,
            occurred_at=occurred_at,
            next_command=next_command,
        )
        await workflow_unit_of_work.outbox.append_event(progress_event)
        appended_event_count = 1

        if decision is DraftClaimCompactionProgressDecision.ALL_GROUPS_COMPACTED:
            await workflow_unit_of_work.outbox.append_event(
                _all_groups_compacted_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    summary=summary,
                    occurred_at=occurred_at,
                    next_command=next_command,
                )
            )
            appended_event_count += 1
        elif decision is DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE:
            await workflow_unit_of_work.outbox.append_event(
                _waiting_user_choice_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    summary=summary,
                    occurred_at=occurred_at,
                )
            )
            appended_event_count += 1

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            summary=summary,
            decision=decision,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                summary=summary,
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
    summary: DraftClaimCompactionProgressSummary,
) -> DraftClaimCompactionProgressDecision:
    if summary.has_waiting_user_model_choice:
        return DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE
    if summary.all_groups_done and not summary.has_active_compaction_work_items:
        return DraftClaimCompactionProgressDecision.ALL_GROUPS_COMPACTED
    if summary.has_due_compaction_work_items:
        return DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_NOW
    if summary.has_future_waiting_work:
        return DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_LATER
    return DraftClaimCompactionProgressDecision.ACTIVE


def _next_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    summary: DraftClaimCompactionProgressSummary,
    decision: DraftClaimCompactionProgressDecision,
    occurred_at: datetime,
) -> WorkflowCommand | None:
    policy = current_llm_dispatch_ownership_policy()
    if policy.draft_claim_compaction_capacity_queue_owns_dispatch and decision in {
        DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_NOW,
        DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_LATER,
    }:
        return None

    if decision is DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_NOW:
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            scheduled_work_item_count=summary.due_waiting_work_item_count,
            run_after=occurred_at,
            occurred_at=occurred_at,
            suffix="now",
        )

    if decision is DraftClaimCompactionProgressDecision.PREPARE_NEXT_BATCH_LATER:
        if summary.next_due_at is None:
            raise ValueError("next_due_at is required for delayed compaction prepare")
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            scheduled_work_item_count=summary.active_work_item_count,
            run_after=summary.next_due_at,
            occurred_at=occurred_at,
            suffix=f"later:{summary.next_due_at.isoformat()}",
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
            "summary": summary.to_payload(),
            "caused_by_command_id": workflow_command.command_id.value,
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


def _progress_reconciled_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    summary: DraftClaimCompactionProgressSummary,
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
            "summary": summary.to_payload(),
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
    summary: DraftClaimCompactionProgressSummary,
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
            "summary": summary.to_payload(),
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
    summary: DraftClaimCompactionProgressSummary,
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
            "summary": summary.to_payload(),
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    summary: DraftClaimCompactionProgressSummary,
    decision: DraftClaimCompactionProgressDecision,
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    for key, value in summary.to_payload().items():
        if isinstance(value, int):
            domain_counters[f"draft_claim_compaction_{key}"] = value

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
            workflow_status=(
                "BLOCKED"
                if decision
                is DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE
                else "RUNNING"
            ),
            total_work_items=summary.group_count,
            scheduled_work_items=summary.group_count,
            running_work_items=summary.active_group_count,
            completed_work_items=summary.done_group_count,
            deferred_work_items=summary.deferred_work_item_count,
            retryable_failed_work_items=summary.retryable_failed_work_item_count,
            terminal_failed_work_items=summary.terminal_failed_work_item_count,
            blocked_work_items=summary.waiting_user_model_choice_group_count,
            domain_counters=domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        )
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    summary: DraftClaimCompactionProgressSummary,
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
            is DraftClaimCompactionProgressDecision.WAITING_USER_MODEL_CHOICE
            else WorkflowTimelineSeverity.INFO
        ),
        message=_timeline_message(decision),
        payload_summary={
            "workflow_run_id": workflow_run_id,
            "decision": decision.value,
            "summary": summary.to_payload(),
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
    return "Draft claim compaction progress reconciled"


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
