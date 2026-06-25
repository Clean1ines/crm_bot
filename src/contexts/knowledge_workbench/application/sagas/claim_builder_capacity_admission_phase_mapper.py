from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityWindowAdmissionPassResult,
    CapacityWindowAdmissionSkippedReason,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
    CapacityAdmissionPhaseExecuteCommandSummary,
    CapacityAdmissionPhaseMapperPort,
    CapacityAdmissionPhaseMappingDecision,
    CapacityAdmissionPhaseMappingPlan,
    CapacityAdmissionPhaseProgressSummary,
    CapacityAdmissionPhaseWorkflowEventSummary,
)


@dataclass(frozen=True, slots=True)
class ClaimBuilderCapacityAdmissionPhaseMapper(CapacityAdmissionPhaseMapperPort):
    async def map_admission_result(
        self,
        *,
        admission_result: CapacityWindowAdmissionPassResult,
        profile=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
        occurred_at: datetime,
    ) -> CapacityAdmissionPhaseMappingPlan:
        if profile != CLAIM_BUILDER_ADMISSION_PHASE_PROFILE:
            raise ValueError("claim-builder mapper requires claim-builder profile")

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
                skipped_reason=admission_result.skipped_reason.value
                if admission_result.skipped_reason is not None
                else None,
            ),
            occurred_at=occurred_at,
        )


def _decision_from_admission_result(
    admission_result: CapacityWindowAdmissionPassResult,
) -> CapacityAdmissionPhaseMappingDecision:
    if not admission_result.skipped:
        return CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED

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
        is CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED
    ):
        return CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED
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
    raise ValueError("unsupported claim-builder admission skipped reason")


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
                    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.execute_command_type
                ),
                command_ref=_execute_command_ref(
                    workflow_run_id=admission_result.workflow_run_id,
                    work_item_id=attempt.work_item_id,
                    attempt_id=attempt.attempt_id,
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
                    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.execute_command_type
                ),
                command_ref=command_ref,
                workflow_run_id=admission_result.workflow_run_id,
                work_item_id=work_item_id,
                attempt_id=attempt_id,
            ),
        )

    return tuple(summaries)


def _event_type_for_decision(decision: CapacityAdmissionPhaseMappingDecision) -> str:
    if decision is CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED:
        return CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.dispatch_prepared_event_type
    if decision is CapacityAdmissionPhaseMappingDecision.CAPACITY_WAITING:
        return "ClaimBuilderCapacityWaiting"
    if decision is CapacityAdmissionPhaseMappingDecision.NO_FITTING_WORK_ITEM:
        return "ClaimBuilderNoFittingWorkItem"
    if decision is CapacityAdmissionPhaseMappingDecision.ACTIVE_LEASED_WAIT:
        return "ClaimBuilderActiveLeasedWait"
    if decision is CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED:
        return "ClaimBuilderSourceSplitRequired"
    if decision is CapacityAdmissionPhaseMappingDecision.PROJECTION_CONFLICT:
        return "ClaimBuilderCapacityProjectionConflict"
    if decision is CapacityAdmissionPhaseMappingDecision.EXECUTION_LEASE_LOST:
        return "ClaimBuilderExecutionLeaseLost"
    raise ValueError("unsupported claim-builder phase mapping decision")


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
) -> str:
    return (
        "workflow-command:"
        f"{workflow_run_id}:"
        "ExecuteClaimBuilderSection:"
        f"{work_item_id}:"
        f"{attempt_id}"
    )


def _parse_appended_execute_command_ref(command_ref: str) -> tuple[str, str]:
    parts = command_ref.split(":")
    if len(parts) < 2:
        raise ValueError("execute command ref must include work item and attempt ids")
    return parts[-2], parts[-1]
