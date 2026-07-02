from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
    WorkItemProgressSummary,
)
from src.contexts.knowledge_workbench.extraction.application.ports.claim_builder_retry_action_read_repository_port import (
    ClaimBuilderRetryActionReadRepositoryPort,
    WorkItemRetryActionSummary,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
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
    CLAIM_BUILDER_SPLIT_REQUIRED = "CLAIM_BUILDER_SPLIT_REQUIRED"
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
        claim_builder_retry_action_read_repository: (
            ClaimBuilderRetryActionReadRepositoryPort
        ),
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
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
        retry_action_summary = (
            await claim_builder_retry_action_read_repository.summarize_retry_actions(
                workflow_run_id=workflow_run_id,
                work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
                now=occurred_at,
            )
        )
        decision = _decide(
            summary=summary,
            retry_action_summary=retry_action_summary,
            now=occurred_at,
        )

        next_command = _next_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            decision=decision,
            summary=summary,
            retry_action_summary=retry_action_summary,
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
            retry_action_summary=retry_action_summary,
            next_command=next_command,
            occurred_at=occurred_at,
        )
        persisted_event = await workflow_unit_of_work.outbox.append_event(event)
        appended_event_count = 1
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(persisted_event)

        if (
            decision
            is ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED
            and _all_sections_extracted_success(summary)
        ):
            all_sections_event = _all_sections_extracted_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                summary=summary,
                occurred_at=occurred_at,
            )
            persisted_all_sections_event = (
                await workflow_unit_of_work.outbox.append_event(all_sections_event)
            )
            appended_event_count += 1
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(
                    persisted_all_sections_event
                )

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            decision=decision,
            summary=summary,
            retry_action_summary=retry_action_summary,
            occurred_at=occurred_at,
        )

        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                decision=decision,
                summary=summary,
                retry_action_summary=retry_action_summary,
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
            appended_event_count=appended_event_count,
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
    *,
    summary: WorkItemProgressSummary,
    retry_action_summary: WorkItemRetryActionSummary,
    now: datetime,
) -> ClaimBuilderProgressReconcileDecision:
    if retry_action_summary.split_required_count > 0:
        return ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SPLIT_REQUIRED

    if _selected_retry_plan(retry_action_summary) is not None:
        if (
            retry_action_summary.next_run_after is not None
            and retry_action_summary.next_run_after > now
        ):
            return ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_LATER
        if summary.due_waiting_count > 0:
            return ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_NOW

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


def _all_sections_extracted_success(summary: WorkItemProgressSummary) -> bool:
    return summary.total_count > 0 and summary.completed_count >= summary.total_count


def _next_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    decision: ClaimBuilderProgressReconcileDecision,
    summary: WorkItemProgressSummary,
    retry_action_summary: WorkItemRetryActionSummary,
    occurred_at: datetime,
) -> WorkflowCommand | None:
    selected_retry_plan = _selected_retry_plan(retry_action_summary)
    prepare_suffix_scope = _prepare_command_suffix_scope(
        selected_retry_plan=selected_retry_plan,
        scheduled_work_item_count=summary.total_count,
    )
    causation_scope = (
        None
        if selected_retry_plan is not None
        else _prepare_command_causation_scope(workflow_command)
    )

    if decision is ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_NOW:
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            summary=summary,
            retry_action_summary=retry_action_summary,
            selected_retry_plan=selected_retry_plan,
            run_after=occurred_at,
            occurred_at=occurred_at,
            suffix=_prepare_command_idempotency_suffix(
                prefix="now",
                prepare_suffix_scope=prepare_suffix_scope,
                causation_scope=causation_scope,
            ),
        )

    if decision is ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_LATER:
        next_due_at = retry_action_summary.next_run_after or summary.next_due_at
        if next_due_at is None:
            raise ValueError("next_due_at is required for delayed prepare decision")
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            summary=summary,
            retry_action_summary=retry_action_summary,
            selected_retry_plan=selected_retry_plan,
            run_after=next_due_at,
            occurred_at=occurred_at,
            suffix=_prepare_command_idempotency_suffix(
                prefix="later",
                prepare_suffix_scope=(
                    f"{prepare_suffix_scope}:{next_due_at.isoformat()}"
                ),
                causation_scope=causation_scope,
            ),
        )

    if decision is ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SPLIT_REQUIRED:
        return None

    if (
        decision
        is ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED
        and _all_sections_extracted_success(summary)
    ):
        return _generate_draft_claim_embeddings_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            retry_action_summary=retry_action_summary,
            summary=summary,
            occurred_at=occurred_at,
        )

    return None


def _prepare_command_suffix_scope(
    *,
    selected_retry_plan: str | None,
    scheduled_work_item_count: int,
) -> str:
    strategy_scope = selected_retry_plan or "default"
    return f"{strategy_scope}:scheduled:{scheduled_work_item_count}"


def _prepare_command_idempotency_suffix(
    *,
    prefix: str,
    prepare_suffix_scope: str,
    causation_scope: str | None,
) -> str:
    if causation_scope is None:
        return f"{prefix}:{prepare_suffix_scope}"
    return f"{prefix}:{prepare_suffix_scope}:{causation_scope}"


def _prepare_command_causation_scope(workflow_command: WorkflowCommand) -> str:
    origin_command_id = _optional_payload_text(
        workflow_command.payload,
        "claim_builder_prepare_command_id",
    )
    origin_idempotency_key = _optional_payload_text(
        workflow_command.payload,
        "claim_builder_prepare_idempotency_key",
    )
    if origin_command_id is not None:
        material = origin_command_id
        if origin_idempotency_key is not None:
            material = f"{origin_command_id}:{origin_idempotency_key}"
    else:
        material = f"legacy-reconcile:{workflow_command.command_id.value}"

    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"cause:{digest[:16]}"


def _prepare_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    summary: WorkItemProgressSummary,
    retry_action_summary: WorkItemRetryActionSummary,
    selected_retry_plan: str | None,
    run_after: datetime,
    occurred_at: datetime,
    suffix: str,
) -> WorkflowCommand:
    idempotency_key = f"prepare-claim-builder-dispatch-batch:{workflow_run_id}:{suffix}"
    command_payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "scheduled_work_item_count": summary.total_count,
    }
    if selected_retry_plan is not None:
        command_payload["selected_retry_plan"] = selected_retry_plan
        command_payload["claim_builder_retry_plan"] = selected_retry_plan
        command_payload["retry_plan"] = selected_retry_plan
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
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    summary: WorkItemProgressSummary,
    retry_action_summary: WorkItemRetryActionSummary,
    occurred_at: datetime,
) -> WorkflowCommand:
    source_document_ref = _source_document_ref(
        workflow_command=workflow_command,
        workflow_run_id=workflow_run_id,
    )
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
            "source_document_ref": source_document_ref,
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "summary": summary.to_payload(),
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _source_document_ref(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
) -> str:
    payload_value = _optional_payload_text(
        workflow_command.payload,
        "source_document_ref",
    )
    if payload_value is not None:
        return payload_value

    prefix = "knowledge-extraction:"
    if not workflow_run_id.startswith(prefix):
        raise ValueError("workflow_run_id must include source document ref")

    source_document_ref = workflow_run_id[len(prefix) :]
    if not source_document_ref.strip():
        raise ValueError("source_document_ref must be non-empty")

    return source_document_ref


def _progress_reconciled_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    decision: ClaimBuilderProgressReconcileDecision,
    summary: WorkItemProgressSummary,
    retry_action_summary: WorkItemRetryActionSummary,
    next_command: WorkflowCommand | None,
    occurred_at: datetime,
) -> WorkflowEvent:
    next_run_after = next_command.run_after.isoformat() if next_command else None
    payload = {
        "workflow_run_id": workflow_run_id,
        "operation_key": "reconcile_claim_builder_progress",
        "canonical_phase": (
            KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
        ),
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "decision": decision.value,
        "summary": summary.to_payload(),
        "retry_action_summary": retry_action_summary.to_payload(),
        "selected_retry_plan": _selected_retry_plan(retry_action_summary),
        "next_command_type": next_command.command_type if next_command else None,
        "next_run_after": next_run_after,
    }
    payload_digest = _workflow_event_payload_digest(payload)
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_PROGRESS_RECONCILED.value}:"
            f"{workflow_command.command_id.value}:"
            f"payload:{payload_digest}"
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


def _workflow_event_payload_digest(payload: Mapping[str, object]) -> str:
    material = json.dumps(
        dict(payload),
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _all_sections_extracted_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    summary: WorkItemProgressSummary,
    occurred_at: datetime,
) -> WorkflowEvent:
    payload = {
        "workflow_run_id": workflow_run_id,
        "operation_key": "reconcile_claim_builder_progress",
        "canonical_phase": (
            KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
        ),
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "summary": summary.to_payload(),
        "completed_count": summary.completed_count,
        "total_count": summary.total_count,
        "next_command_type": (
            KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS.value
        ),
    }
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED.value}:"
            f"{workflow_command.command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED.value
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
    retry_action_summary: WorkItemRetryActionSummary,
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
    domain_counters["claim_builder_retry_same_route_pending_count"] = (
        retry_action_summary.retry_same_route_count
    )
    domain_counters["claim_builder_retry_empty_claims_check_model_pending_count"] = (
        retry_action_summary.retry_empty_claims_check_model_count
    )
    domain_counters["claim_builder_retry_fallback_model_pending_count"] = (
        retry_action_summary.retry_fallback_model_count
    )
    domain_counters["claim_builder_retry_larger_output_limit_route_pending_count"] = (
        retry_action_summary.retry_larger_output_limit_route_count
    )
    domain_counters["claim_builder_retry_larger_input_model_pending_count"] = (
        retry_action_summary.retry_larger_input_model_count
    )
    domain_counters["claim_builder_split_required_pending_count"] = (
        retry_action_summary.split_required_count
    )
    domain_counters["claim_builder_pause_for_daily_limit_reset_pending_count"] = (
        retry_action_summary.pause_for_daily_limit_reset_count
    )
    domain_counters[
        "claim_builder_request_user_low_quality_continue_or_wait_pending_count"
    ] = retry_action_summary.request_user_low_quality_continue_or_wait_count

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
    retry_action_summary: WorkItemRetryActionSummary,
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
        message=_timeline_message(retry_action_summary),
        payload_summary={
            "workflow_run_id": workflow_run_id,
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "decision": decision.value,
            "summary": summary.to_payload(),
            "retry_action_summary": retry_action_summary.to_payload(),
            "selected_retry_plan": _selected_retry_plan(retry_action_summary),
            "next_command_type": next_command.command_type if next_command else None,
        },
        occurred_at=occurred_at,
        source_ref=workflow_command.command_type,
    )


def _selected_retry_plan(
    retry_action_summary: WorkItemRetryActionSummary,
) -> str | None:
    if retry_action_summary.retry_larger_input_model_count > 0:
        return "retry_larger_input_limit_route"
    if retry_action_summary.retry_larger_output_limit_route_count > 0:
        return "retry_larger_output_limit_route"
    if _has_retry_strategy(
        retry_action_summary,
        "DAILY_LIMIT_retry_daily_fallback_route",
    ):
        return "DAILY_LIMIT_retry_daily_fallback_route"
    if retry_action_summary.retry_empty_claims_check_model_count > 0:
        return "retry_validation_check_route"
    if retry_action_summary.retry_fallback_model_count > 0:
        return "retry_daily_fallback_route"
    if retry_action_summary.retry_same_route_count > 0:
        return "retry_same_route"
    return None


def _has_retry_strategy(
    retry_action_summary: WorkItemRetryActionSummary,
    strategy: str,
) -> bool:
    return any(record.retry_plan == strategy for record in retry_action_summary.records)


def _timeline_message(
    retry_action_summary: WorkItemRetryActionSummary,
) -> str:
    if _selected_retry_plan(retry_action_summary) is not None:
        return "Claim builder retry action selected"
    if retry_action_summary.split_required_count > 0:
        return "Claim builder split action required"
    return "Claim builder progress reconciled"


def _severity(
    decision: ClaimBuilderProgressReconcileDecision,
    summary: WorkItemProgressSummary,
) -> WorkflowTimelineSeverity:
    if decision in {
        ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_PROGRESS_BLOCKED,
        ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SPLIT_REQUIRED,
    }:
        return WorkflowTimelineSeverity.WARNING
    if summary.terminal_failed_count > 0:
        return WorkflowTimelineSeverity.WARNING
    return WorkflowTimelineSeverity.INFO


def _optional_payload_text(
    payload: Mapping[str, object],
    key: str,
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload {key} must be non-empty text")
    return value


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
