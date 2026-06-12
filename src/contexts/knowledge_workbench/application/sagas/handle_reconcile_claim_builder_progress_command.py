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
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
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


class ClaimBuilderProgressReconcileDecision(StrEnum):
    PREPARE_NEXT_BATCH_NOW = "PREPARE_NEXT_BATCH_NOW"
    PREPARE_NEXT_BATCH_LATER = "PREPARE_NEXT_BATCH_LATER"
    CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED = (
        "CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED"
    )
    CLAIM_BUILDER_PROGRESS_BLOCKED = "CLAIM_BUILDER_PROGRESS_BLOCKED"


class ClaimBuilderProgressReadRepositoryPort(Protocol):
    async def summarize_by_work_kind_and_workflow(
        self,
        *,
        workflow_run_id: str,
        work_kind,
        now: datetime,
    ) -> WorkItemProgressSummary: ...


@dataclass(frozen=True, slots=True)
class HandleReconcileClaimBuilderProgressCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandleReconcileClaimBuilderProgressResult:
    workflow_run_id: str
    decision: str
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.decision, "decision")
        _require_non_negative_int(self.appended_event_count, "appended_event_count")
        _require_non_negative_int(
            self.appended_next_command_count,
            "appended_next_command_count",
        )
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


class HandleReconcileClaimBuilderProgressCommandHandler:
    async def execute(
        self,
        command: HandleReconcileClaimBuilderProgressCommand,
        *,
        work_item_progress_read_repository: WorkItemProgressReadRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleReconcileClaimBuilderProgressResult:
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
        summary = await work_item_progress_read_repository.summarize_by_work_kind_and_workflow(
            workflow_run_id=workflow_run_id,
            work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
            now=occurred_at,
        )
        decision = _decide(summary)

        next_command = _next_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            decision=decision,
            summary=summary,
            occurred_at=occurred_at,
        )
        appended_next_command_count = 0
        if next_command is not None:
            await workflow_unit_of_work.command_log.append_pending_command(next_command)
            appended_next_command_count = 1

        event = _progress_reconciled_event(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            decision=decision,
            summary=summary,
            next_command=next_command,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.outbox.append_event(event)

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            decision=decision,
            summary=summary,
            occurred_at=occurred_at,
        )

        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                decision=decision,
                summary=summary,
                next_command=next_command,
                occurred_at=occurred_at,
            ),
        )

        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return HandleReconcileClaimBuilderProgressResult(
            workflow_run_id=workflow_run_id,
            decision=decision.value,
            appended_event_count=1,
            appended_next_command_count=appended_next_command_count,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS.value
    ):
        raise ValueError(
            "workflow_command command_type must be ReconcileClaimBuilderProgress"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _decide(
    summary: WorkItemProgressSummary,
) -> ClaimBuilderProgressReconcileDecision:
    if summary.due_waiting_count > 0:
        return ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_NOW

    if summary.has_future_waiting_work and summary.next_due_at is not None:
        return ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_LATER

    if (
        summary.total_count > 0
        and summary.terminal_coverage_count >= summary.total_count
    ):
        return ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED

    return ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_PROGRESS_BLOCKED


def _next_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    decision: ClaimBuilderProgressReconcileDecision,
    summary: WorkItemProgressSummary,
    occurred_at: datetime,
) -> WorkflowCommand | None:
    if decision is ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_NOW:
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            summary=summary,
            run_after=occurred_at,
            occurred_at=occurred_at,
            suffix="now",
        )

    if decision is ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_LATER:
        if summary.next_due_at is None:
            raise ValueError("next_due_at is required for delayed prepare decision")
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            summary=summary,
            run_after=summary.next_due_at,
            occurred_at=occurred_at,
            suffix=f"later:{summary.next_due_at.isoformat()}",
        )

    if (
        decision
        is ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED
    ):
        return _generate_draft_claim_embeddings_command(
            workflow_run_id=workflow_run_id,
            summary=summary,
            occurred_at=occurred_at,
        )

    return None


def _prepare_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    summary: WorkItemProgressSummary,
    run_after: datetime,
    occurred_at: datetime,
    suffix: str,
) -> WorkflowCommand:
    idempotency_key = f"prepare-claim-builder-dispatch-batch:{workflow_run_id}:{suffix}"
    command_payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "scheduled_work_item_count": summary.due_waiting_count,
        "summary": summary.to_payload(),
    }
    dispatch_preparation = workflow_command.payload.get("llm_dispatch_preparation")
    if dispatch_preparation is not None:
        if not isinstance(dispatch_preparation, Mapping):
            raise ValueError("llm_dispatch_preparation must be mapping")
        command_payload["llm_dispatch_preparation"] = dict(dispatch_preparation)

    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=command_payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=run_after,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _generate_draft_claim_embeddings_command(
    *,
    workflow_run_id: str,
    summary: WorkItemProgressSummary,
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = f"generate-draft-claim-embeddings:{workflow_run_id}"
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={
            "workflow_run_id": workflow_run_id,
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "summary": summary.to_payload(),
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _progress_reconciled_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    decision: ClaimBuilderProgressReconcileDecision,
    summary: WorkItemProgressSummary,
    next_command: WorkflowCommand | None,
    occurred_at: datetime,
) -> WorkflowEvent:
    next_run_after = next_command.run_after.isoformat() if next_command else None
    payload = {
        "workflow_run_id": workflow_run_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "decision": decision.value,
        "summary": summary.to_payload(),
        "next_command_type": next_command.command_type if next_command else None,
        "next_run_after": next_run_after,
    }
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_PROGRESS_RECONCILED.value}:"
            f"{workflow_command.command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_PROGRESS_RECONCILED.value
        ),
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    decision: ClaimBuilderProgressReconcileDecision,
    summary: WorkItemProgressSummary,
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    for key, value in summary.to_payload().items():
        if isinstance(value, int):
            domain_counters[f"claim_builder_{key}"] = value
    domain_counters["claim_builder_terminal_coverage_count"] = (
        summary.terminal_coverage_count
    )
    domain_counters["claim_builder_due_waiting_count"] = summary.due_waiting_count

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            workflow_status=(
                "BLOCKED"
                if decision
                is ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_PROGRESS_BLOCKED
                else "RUNNING"
            ),
            total_work_items=summary.total_count,
            scheduled_work_items=summary.total_count,
            running_work_items=summary.leased_count,
            completed_work_items=summary.completed_count,
            deferred_work_items=summary.deferred_count,
            retryable_failed_work_items=summary.retryable_failed_count,
            terminal_failed_work_items=summary.terminal_failed_count,
            blocked_work_items=summary.user_action_required_count,
            domain_counters=domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        ),
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    decision: ClaimBuilderProgressReconcileDecision,
    summary: WorkItemProgressSummary,
    next_command: WorkflowCommand | None,
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            f"ClaimBuilderProgressReconciled:{workflow_command.command_id.value}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_PROGRESS_RECONCILED.value,
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        severity=_severity(decision, summary),
        message="Claim builder progress reconciled",
        payload_summary={
            "workflow_run_id": workflow_run_id,
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "decision": decision.value,
            "summary": summary.to_payload(),
            "next_command_type": next_command.command_type if next_command else None,
        },
        occurred_at=occurred_at,
        source_ref=workflow_command.command_type,
    )


def _severity(
    decision: ClaimBuilderProgressReconcileDecision,
    summary: WorkItemProgressSummary,
) -> WorkflowTimelineSeverity:
    if decision is ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_PROGRESS_BLOCKED:
        return WorkflowTimelineSeverity.WARNING
    if summary.terminal_failed_count > 0:
        return WorkflowTimelineSeverity.WARNING
    return WorkflowTimelineSeverity.INFO


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


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
