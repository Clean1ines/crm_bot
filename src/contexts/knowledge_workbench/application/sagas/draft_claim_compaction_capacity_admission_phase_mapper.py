from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionDispatchContextSummary,
    CapacityWindowAdmissionPassResult,
    CapacityWindowAdmissionSkippedReason,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
    CapacityAdmissionPhaseExecuteCommandSummary,
    CapacityAdmissionPhaseMapperPort,
    CapacityAdmissionPhaseMappingDecision,
    CapacityAdmissionPhaseMappingPlan,
    CapacityAdmissionPhaseMappingProfile,
    CapacityAdmissionPhaseProgressSummary,
    CapacityAdmissionPhaseWorkflowEventSummary,
)


USER_MODEL_CHOICE_FRONTEND_EVENT_KIND = "capacity_admission_user_model_choice_required"


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionCapacityAdmissionPhaseMapper(
    CapacityAdmissionPhaseMapperPort
):
    async def map_admission_result(
        self,
        *,
        admission_result: CapacityWindowAdmissionPassResult,
        profile: CapacityAdmissionPhaseMappingProfile = (
            DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE
        ),
        occurred_at: datetime,
    ) -> CapacityAdmissionPhaseMappingPlan:
        if profile != DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE:
            raise ValueError(
                "draft-claim-compaction mapper requires compaction profile"
            )

        decision = _decision_from_admission_result(admission_result)
        workflow_events = _workflow_events_for_decision(
            admission_result=admission_result,
            decision=decision,
        )
        execute_commands = _execute_commands_for_decision(
            admission_result=admission_result,
            decision=decision,
        )
        frontend_events = (
            (admission_result.frontend_event_summary,)
            if admission_result.frontend_event_summary is not None
            else ()
        )
        return CapacityAdmissionPhaseMappingPlan(
            profile=profile,
            admission_result=admission_result,
            decision=decision,
            workflow_events=workflow_events,
            execute_commands=execute_commands,
            frontend_events=frontend_events,
            progress_summary=CapacityAdmissionPhaseProgressSummary(
                workflow_run_id=admission_result.workflow_run_id,
                phase=profile.phase,
                operation_key=profile.operation_key,
                prepared_dispatch_count=len(admission_result.admitted_items),
                appended_event_count=len(workflow_events),
                appended_next_command_count=len(execute_commands),
                skipped_reason=_progress_skipped_reason(
                    admission_result=admission_result,
                    decision=decision,
                ),
            ),
            occurred_at=occurred_at,
        )


def _decision_from_admission_result(
    admission_result: CapacityWindowAdmissionPassResult,
) -> CapacityAdmissionPhaseMappingDecision:
    if not admission_result.skipped:
        return CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED

    if _requires_user_model_choice(admission_result):
        return CapacityAdmissionPhaseMappingDecision.USER_MODEL_CHOICE_REQUIRED
    if (
        admission_result.skipped_reason
        is CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED
    ):
        return CapacityAdmissionPhaseMappingDecision.CAPACITY_WAITING
    if (
        admission_result.skipped_reason
        is CapacityWindowAdmissionSkippedReason.NO_FITTING_WORK_ITEM
    ):
        return CapacityAdmissionPhaseMappingDecision.NO_FITTING_WORK_ITEM
    if (
        admission_result.skipped_reason
        is CapacityWindowAdmissionSkippedReason.ACTIVE_LEASED_WAIT
    ):
        return CapacityAdmissionPhaseMappingDecision.ACTIVE_LEASED_WAIT
    if (
        admission_result.skipped_reason
        is CapacityWindowAdmissionSkippedReason.PROJECTION_CONFLICT
    ):
        return CapacityAdmissionPhaseMappingDecision.PROJECTION_CONFLICT
    if (
        admission_result.skipped_reason
        is CapacityWindowAdmissionSkippedReason.EXECUTION_LEASE_LOST
    ):
        return CapacityAdmissionPhaseMappingDecision.EXECUTION_LEASE_LOST
    if (
        admission_result.skipped_reason
        is CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED
    ):
        raise ValueError(
            "draft-claim-compaction does not support source_split_required"
        )
    raise ValueError("unsupported draft-claim-compaction admission skipped reason")


def _requires_user_model_choice(
    admission_result: CapacityWindowAdmissionPassResult,
) -> bool:
    return (
        admission_result.frontend_event_summary is not None
        and admission_result.frontend_event_summary.event_kind
        == USER_MODEL_CHOICE_FRONTEND_EVENT_KIND
    )


def _workflow_events_for_decision(
    *,
    admission_result: CapacityWindowAdmissionPassResult,
    decision: CapacityAdmissionPhaseMappingDecision,
) -> tuple[CapacityAdmissionPhaseWorkflowEventSummary, ...]:
    event_type = _event_type_for_decision(decision)
    return (
        CapacityAdmissionPhaseWorkflowEventSummary(
            event_type=event_type,
            event_id=_workflow_event_id(
                workflow_run_id=admission_result.workflow_run_id,
                event_type=event_type,
                decision=decision,
            ),
            workflow_run_id=admission_result.workflow_run_id,
            work_item_ids=tuple(
                item.work_item_id for item in admission_result.admitted_items
            ),
            attempt_ids=tuple(
                attempt.attempt_id for attempt in admission_result.started_attempts
            ),
            projection_event_ids=tuple(
                projection.event_id for projection in admission_result.projection_leases
            ),
        ),
    )


def _execute_commands_for_decision(
    *,
    admission_result: CapacityWindowAdmissionPassResult,
    decision: CapacityAdmissionPhaseMappingDecision,
) -> tuple[CapacityAdmissionPhaseExecuteCommandSummary, ...]:
    if decision is not CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED:
        return ()

    summaries: list[CapacityAdmissionPhaseExecuteCommandSummary] = []
    for attempt in admission_result.started_attempts:
        summaries.append(
            CapacityAdmissionPhaseExecuteCommandSummary(
                command_type=(
                    DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.execute_command_type
                ),
                command_ref=_execute_command_ref(
                    workflow_run_id=admission_result.workflow_run_id,
                    work_item_id=attempt.work_item_id,
                    attempt_id=attempt.attempt_id,
                    dispatch_context=_dispatch_context_for_work_item(
                        admission_result=admission_result,
                        work_item_id=attempt.work_item_id,
                    ),
                ),
                workflow_run_id=admission_result.workflow_run_id,
                work_item_id=attempt.work_item_id,
                attempt_id=attempt.attempt_id,
            ),
        )

    for command_ref in admission_result.appended_execute_command_refs:
        work_item_id, attempt_id = _parse_appended_execute_command_ref(command_ref)
        summaries.append(
            CapacityAdmissionPhaseExecuteCommandSummary(
                command_type=(
                    DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.execute_command_type
                ),
                command_ref=command_ref,
                workflow_run_id=admission_result.workflow_run_id,
                work_item_id=work_item_id,
                attempt_id=attempt_id,
            ),
        )

    return tuple(summaries)


def _dispatch_context_for_work_item(
    *,
    admission_result: CapacityWindowAdmissionPassResult,
    work_item_id: str,
) -> CapacityAdmissionDispatchContextSummary | None:
    for admitted_item in admission_result.admitted_items:
        if admitted_item.work_item_id == work_item_id:
            return admitted_item.dispatch_context
    return None


def _event_type_for_decision(decision: CapacityAdmissionPhaseMappingDecision) -> str:
    if decision is CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED:
        return (
            DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.dispatch_prepared_event_type
        )
    if decision is CapacityAdmissionPhaseMappingDecision.CAPACITY_WAITING:
        return "DraftClaimCompactionCapacityWaiting"
    if decision is CapacityAdmissionPhaseMappingDecision.NO_FITTING_WORK_ITEM:
        return "DraftClaimCompactionNoFittingWorkItem"
    if decision is CapacityAdmissionPhaseMappingDecision.ACTIVE_LEASED_WAIT:
        return "DraftClaimCompactionActiveLeasedWait"
    if decision is CapacityAdmissionPhaseMappingDecision.USER_MODEL_CHOICE_REQUIRED:
        return "DraftClaimCompactionUserModelChoiceRequired"
    if decision is CapacityAdmissionPhaseMappingDecision.PROJECTION_CONFLICT:
        return "DraftClaimCompactionCapacityProjectionConflict"
    if decision is CapacityAdmissionPhaseMappingDecision.EXECUTION_LEASE_LOST:
        return "DraftClaimCompactionExecutionLeaseLost"
    raise ValueError("unsupported draft-claim-compaction phase mapping decision")


def _progress_skipped_reason(
    *,
    admission_result: CapacityWindowAdmissionPassResult,
    decision: CapacityAdmissionPhaseMappingDecision,
) -> str | None:
    if not admission_result.skipped:
        return None
    if decision is CapacityAdmissionPhaseMappingDecision.USER_MODEL_CHOICE_REQUIRED:
        return "user_model_choice_required"
    if admission_result.skipped_reason is None:
        return None
    return admission_result.skipped_reason.value


def _workflow_event_id(
    *,
    workflow_run_id: str,
    event_type: str,
    decision: CapacityAdmissionPhaseMappingDecision,
) -> str:
    return f"workflow-event:{workflow_run_id}:{event_type}:{decision.value}"


def _execute_command_ref(
    *,
    workflow_run_id: str,
    work_item_id: str,
    attempt_id: str,
    dispatch_context: CapacityAdmissionDispatchContextSummary | None,
) -> str:
    context_suffix = ""
    if dispatch_context is not None:
        context_suffix = _dispatch_context_suffix(dispatch_context)
    return (
        "workflow-command:"
        f"{workflow_run_id}:"
        "ExecuteDraftClaimCompaction:"
        f"{work_item_id}:"
        f"{attempt_id}"
        f"{context_suffix}"
    )


def _dispatch_context_suffix(
    dispatch_context: CapacityAdmissionDispatchContextSummary,
) -> str:
    parts: list[str] = []
    if dispatch_context.group_ref is not None:
        parts.append(f"group={dispatch_context.group_ref}")
    if dispatch_context.batch_ref is not None:
        parts.append(f"batch={dispatch_context.batch_ref}")
    if dispatch_context.round_index is not None:
        parts.append(f"round={dispatch_context.round_index}")
    if not parts:
        return ""
    return ":" + ":".join(parts)


def _parse_appended_execute_command_ref(command_ref: str) -> tuple[str, str]:
    parts = command_ref.split(":")
    if len(parts) < 2:
        raise ValueError("execute command ref must include work item and attempt ids")
    return parts[-2], parts[-1]
