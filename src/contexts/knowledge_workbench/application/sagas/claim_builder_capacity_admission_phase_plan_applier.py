from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionDispatchContextSummary,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
    CapacityAdmissionPhaseExecuteCommandSummary,
    CapacityAdmissionPhaseMappingDecision,
    CapacityAdmissionPhaseMappingPlan,
    CapacityAdmissionPhaseWorkflowEventSummary,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
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
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)


@dataclass(frozen=True, slots=True)
class ApplyClaimBuilderCapacityAdmissionPhasePlanCommand:
    workflow_command: WorkflowCommand
    mapping_plan: CapacityAdmissionPhaseMappingPlan

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")
        if not isinstance(self.mapping_plan, CapacityAdmissionPhaseMappingPlan):
            raise TypeError("mapping_plan must be CapacityAdmissionPhaseMappingPlan")


@dataclass(frozen=True, slots=True)
class ApplyClaimBuilderCapacityAdmissionPhasePlanResult:
    workflow_run_id: str
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_negative_int(self.appended_event_count, "appended_event_count")
        _require_non_negative_int(
            self.appended_next_command_count,
            "appended_next_command_count",
        )
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


@dataclass(frozen=True, slots=True)
class ClaimBuilderCapacityAdmissionPhasePlanApplier:
    async def execute(
        self,
        command: ApplyClaimBuilderCapacityAdmissionPhasePlanCommand,
        *,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> ApplyClaimBuilderCapacityAdmissionPhasePlanResult:
        workflow_command = command.workflow_command
        mapping_plan = command.mapping_plan
        _validate_workflow_command(workflow_command)
        _validate_mapping_plan(mapping_plan)

        occurred_at = mapping_plan.occurred_at or _utc_now()
        appended_event_count = 0
        appended_next_command_count = 0

        for workflow_event_summary in mapping_plan.workflow_events:
            try:
                persisted_event = await workflow_unit_of_work.outbox.append_event(
                    _workflow_event_from_summary(
                        workflow_command=workflow_command,
                        mapping_plan=mapping_plan,
                        workflow_event_summary=workflow_event_summary,
                        occurred_at=occurred_at,
                    )
                )
            except ValueError as exc:
                if "event_id conflict has different payload" not in str(exc):
                    raise
                persisted_event = None

            if persisted_event is not None:
                if frontend_event_projection_writer is not None:
                    await frontend_event_projection_writer.execute(persisted_event)
                appended_event_count += 1

        for execute_command_summary in mapping_plan.execute_commands:
            await workflow_unit_of_work.command_log.append_pending_command(
                _execute_command_from_summary(
                    workflow_command=workflow_command,
                    mapping_plan=mapping_plan,
                    execute_command_summary=execute_command_summary,
                    occurred_at=occurred_at,
                )
            )
            appended_next_command_count += 1

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            mapping_plan=mapping_plan,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                mapping_plan=mapping_plan,
                appended_event_count=appended_event_count,
                appended_next_command_count=appended_next_command_count,
                occurred_at=occurred_at,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return ApplyClaimBuilderCapacityAdmissionPhasePlanResult(
            workflow_run_id=mapping_plan.admission_result.workflow_run_id,
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    ):
        raise ValueError(
            "workflow_command command_type must be PrepareClaimBuilderDispatchBatch"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _validate_mapping_plan(mapping_plan: CapacityAdmissionPhaseMappingPlan) -> None:
    if mapping_plan.profile != CLAIM_BUILDER_ADMISSION_PHASE_PROFILE:
        raise ValueError("mapping_plan must use claim-builder admission profile")
    if (
        mapping_plan.admission_result.workflow_run_id
        != mapping_plan.progress_summary.workflow_run_id
        if mapping_plan.progress_summary is not None
        else False
    ):
        raise ValueError("mapping_plan progress workflow_run_id mismatch")


def _workflow_event_from_summary(
    *,
    workflow_command: WorkflowCommand,
    mapping_plan: CapacityAdmissionPhaseMappingPlan,
    workflow_event_summary: CapacityAdmissionPhaseWorkflowEventSummary,
    occurred_at: datetime,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(workflow_event_summary.event_id),
        event_type=workflow_event_summary.event_type,
        workflow_run_id=workflow_event_summary.workflow_run_id,
        payload=_workflow_event_payload(
            mapping_plan=mapping_plan,
            workflow_event_summary=workflow_event_summary,
        ),
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.idempotency_key.value,
    )


def _workflow_event_payload(
    *,
    mapping_plan: CapacityAdmissionPhaseMappingPlan,
    workflow_event_summary: CapacityAdmissionPhaseWorkflowEventSummary,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "workflow_run_id": mapping_plan.admission_result.workflow_run_id,
        "phase": mapping_plan.profile.phase,
        "operation_key": mapping_plan.profile.operation_key,
        "work_kind": mapping_plan.profile.work_kind,
        "decision": mapping_plan.decision.value,
        "prepared_dispatch_count": mapping_plan.prepared_dispatch_count,
        "work_item_ids": workflow_event_summary.work_item_ids,
        "dispatch_attempt_ids": workflow_event_summary.attempt_ids,
        "projection_event_ids": tuple(
            str(event_id) for event_id in workflow_event_summary.projection_event_ids
        ),
    }
    if mapping_plan.admission_result.skipped_reason is not None:
        payload["skipped_reason"] = mapping_plan.admission_result.skipped_reason.value
    if (
        mapping_plan.decision
        is CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED
    ):
        payload["source_split_required"] = True
        if mapping_plan.admission_result.safe_preflight_summary is not None:
            payload["source_unit_refs"] = (
                mapping_plan.admission_result.safe_preflight_summary.source_unit_refs
            )
            payload["affected_work_item_refs"] = (
                mapping_plan.admission_result.safe_preflight_summary.affected_work_item_refs
            )
            payload["input_size_preflight_decision"] = (
                mapping_plan.admission_result.safe_preflight_summary.decision
            )
            payload["input_size_preflight_reason"] = (
                mapping_plan.admission_result.safe_preflight_summary.reason
            )
            payload["active_model_ref"] = (
                mapping_plan.admission_result.safe_preflight_summary.active_model_ref
            )
    return payload


def _execute_command_from_summary(
    *,
    workflow_command: WorkflowCommand,
    mapping_plan: CapacityAdmissionPhaseMappingPlan,
    execute_command_summary: CapacityAdmissionPhaseExecuteCommandSummary,
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = (
        "execute-claim-builder-section:"
        f"{execute_command_summary.workflow_run_id}:"
        f"{execute_command_summary.attempt_id}"
    )
    payload = _execute_command_payload(
        workflow_command=workflow_command,
        mapping_plan=mapping_plan,
        execute_command_summary=execute_command_summary,
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value,
        workflow_run_id=execute_command_summary.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _execute_command_payload(
    *,
    workflow_command: WorkflowCommand,
    mapping_plan: CapacityAdmissionPhaseMappingPlan,
    execute_command_summary: CapacityAdmissionPhaseExecuteCommandSummary,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "workflow_run_id": execute_command_summary.workflow_run_id,
        "work_kind": mapping_plan.profile.work_kind,
        "dispatch_attempt_id": execute_command_summary.attempt_id,
        "work_item_id": execute_command_summary.work_item_id,
        "claim_builder_prepare_command_id": workflow_command.command_id.value,
        "claim_builder_prepare_idempotency_key": workflow_command.idempotency_key.value,
    }
    for copied_key in (
        "source_document_ref",
        "scheduled_work_item_count",
        "active_model_ref",
        "retry_plan",
        "selected_retry_plan",
        "claim_builder_retry_plan",
    ):
        copied_value = workflow_command.payload.get(copied_key)
        if copied_value is not None:
            payload[copied_key] = copied_value

    dispatch_preparation = workflow_command.payload.get("llm_dispatch_preparation")
    if dispatch_preparation is not None:
        if not isinstance(dispatch_preparation, Mapping):
            raise ValueError("llm_dispatch_preparation must be mapping")
        payload["llm_dispatch_preparation"] = dict(dispatch_preparation)

    dispatch_context = _dispatch_context_for_work_item(
        mapping_plan=mapping_plan,
        work_item_id=execute_command_summary.work_item_id,
    )
    if dispatch_context is not None:
        _copy_dispatch_context(payload, dispatch_context)

    return payload


def _dispatch_context_for_work_item(
    *,
    mapping_plan: CapacityAdmissionPhaseMappingPlan,
    work_item_id: str,
) -> CapacityAdmissionDispatchContextSummary | None:
    for admitted_item in mapping_plan.admission_result.admitted_items:
        if admitted_item.work_item_id == work_item_id:
            return admitted_item.dispatch_context
    return None


def _copy_dispatch_context(
    payload: dict[str, object],
    dispatch_context: CapacityAdmissionDispatchContextSummary,
) -> None:
    if dispatch_context.source_ref is not None:
        payload["source_ref"] = dispatch_context.source_ref
    if dispatch_context.source_unit_ref is not None:
        payload["source_unit_ref"] = dispatch_context.source_unit_ref


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    mapping_plan: CapacityAdmissionPhaseMappingPlan,
    occurred_at: datetime,
) -> None:
    workflow_run_id = mapping_plan.admission_result.workflow_run_id
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    existing_domain_counters = (
        dict(existing.domain_counters) if existing is not None else {}
    )
    existing_domain_counters["prepared_dispatch_count"] = (
        mapping_plan.prepared_dispatch_count
    )
    existing_domain_counters["claim_builder_source_split_required_count"] = (
        1
        if mapping_plan.decision
        is CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED
        else 0
    )

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            workflow_status="RUNNING",
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=(
                existing.scheduled_work_items if existing is not None else 0
            ),
            running_work_items=max(
                existing.running_work_items if existing is not None else 0,
                mapping_plan.prepared_dispatch_count,
            ),
            completed_work_items=(
                existing.completed_work_items if existing is not None else 0
            ),
            deferred_work_items=(
                existing.deferred_work_items if existing is not None else 0
            ),
            retryable_failed_work_items=(
                existing.retryable_failed_work_items if existing is not None else 0
            ),
            terminal_failed_work_items=(
                existing.terminal_failed_work_items if existing is not None else 0
            ),
            blocked_work_items=(
                existing.blocked_work_items if existing is not None else 0
            ),
            domain_counters=existing_domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        ),
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    mapping_plan: CapacityAdmissionPhaseMappingPlan,
    appended_event_count: int,
    appended_next_command_count: int,
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_command.workflow_run_id}:"
            "ClaimBuilderCapacityAdmissionPhasePlanApplied:"
            f"{occurred_at.isoformat()}"
        ),
        workflow_run_id=workflow_command.workflow_run_id,
        event_type="ClaimBuilderCapacityAdmissionPhasePlanApplied",
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        severity=WorkflowTimelineSeverity.INFO,
        message="Claim builder capacity admission phase plan applied",
        payload_summary={
            "workflow_run_id": workflow_command.workflow_run_id,
            "decision": mapping_plan.decision.value,
            "prepared_dispatch_count": mapping_plan.prepared_dispatch_count,
            "appended_event_count": appended_event_count,
            "appended_next_command_count": appended_next_command_count,
        },
        occurred_at=occurred_at,
        source_ref=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
