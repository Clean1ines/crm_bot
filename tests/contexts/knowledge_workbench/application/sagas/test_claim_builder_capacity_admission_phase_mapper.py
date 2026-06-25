from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionAdmittedItemSummary,
    CapacityAdmissionFrontendEventSummary,
    CapacityAdmissionLaneSummary,
    CapacityAdmissionProjectionLeaseSummary,
    CapacityAdmissionStartedAttemptSummary,
    CapacityWindowAdmissionLogEvent,
    CapacityWindowAdmissionPassResult,
    CapacityWindowAdmissionSkippedReason,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
    CapacityAdmissionPhaseMappingDecision,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_capacity_admission_phase_mapper import (
    ClaimBuilderCapacityAdmissionPhaseMapper,
)


def _now() -> datetime:
    return datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def _lane() -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )


def _admitted_result() -> CapacityWindowAdmissionPassResult:
    projection_event_id = UUID("00000000-0000-0000-0000-000000000001")
    return CapacityWindowAdmissionPassResult(
        workflow_run_id="workflow-1",
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        lane=_lane(),
        admitted_items=(
            CapacityAdmissionAdmittedItemSummary(
                work_item_id="work-item-1",
                lane=_lane(),
                selection_kind="fresh",
                estimated_input_tokens=100,
                estimated_output_tokens=20,
                effective_output_cap_tokens=50,
                reserved_total_tokens=150,
            ),
        ),
        projection_leases=(
            CapacityAdmissionProjectionLeaseSummary(
                work_item_id="work-item-1",
                lane=_lane(),
                previous_status="ready",
                status="leased",
                event_id=projection_event_id,
            ),
        ),
        started_attempts=(
            CapacityAdmissionStartedAttemptSummary(
                work_item_id="work-item-1",
                attempt_id="attempt-1",
                attempt_number=1,
            ),
        ),
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_pass_completed",
            workflow_run_id="workflow-1",
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
            lane=_lane(),
            admitted_count=1,
            started_attempt_count=1,
            work_item_ids=("work-item-1",),
            attempt_ids=("attempt-1",),
            projection_event_ids=(projection_event_id,),
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_COMPLETED,
    )


def _skipped_result(
    skipped_reason: CapacityWindowAdmissionSkippedReason,
) -> CapacityWindowAdmissionPassResult:
    return CapacityWindowAdmissionPassResult(
        workflow_run_id="workflow-1",
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        lane=_lane(),
        skipped_reason=skipped_reason,
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_pass_skipped",
            workflow_run_id="workflow-1",
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
            lane=_lane(),
            admitted_count=0,
            started_attempt_count=0,
            skipped_reason=skipped_reason,
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
    )


@pytest.mark.asyncio
async def test_maps_admitted_claim_builder_result_to_dispatch_prepared_plan() -> None:
    plan = await ClaimBuilderCapacityAdmissionPhaseMapper().map_admission_result(
        admission_result=_admitted_result(),
        occurred_at=_now(),
    )

    assert plan.decision is CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED
    assert len(plan.workflow_events) == 1
    assert plan.workflow_events[0].event_type == "ClaimBuilderDispatchBatchPrepared"
    assert plan.workflow_events[0].work_item_ids == ("work-item-1",)
    assert plan.workflow_events[0].attempt_ids == ("attempt-1",)
    assert len(plan.execute_commands) == 1
    assert plan.execute_commands[0].command_type == "ExecuteClaimBuilderSection"
    assert plan.execute_commands[0].work_item_id == "work-item-1"
    assert plan.execute_commands[0].attempt_id == "attempt-1"
    assert plan.progress_summary is not None
    assert plan.progress_summary.prepared_dispatch_count == 1
    assert plan.progress_summary.appended_next_command_count == 1
    assert len(plan.frontend_events) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("skipped_reason", "decision", "event_type"),
    (
        (
            CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            CapacityAdmissionPhaseMappingDecision.CAPACITY_WAITING,
            "ClaimBuilderCapacityWaiting",
        ),
        (
            CapacityWindowAdmissionSkippedReason.NO_FITTING_WORK_ITEM,
            CapacityAdmissionPhaseMappingDecision.NO_FITTING_WORK_ITEM,
            "ClaimBuilderNoFittingWorkItem",
        ),
        (
            CapacityWindowAdmissionSkippedReason.PROJECTION_CONFLICT,
            CapacityAdmissionPhaseMappingDecision.PROJECTION_CONFLICT,
            "ClaimBuilderCapacityProjectionConflict",
        ),
        (
            CapacityWindowAdmissionSkippedReason.EXECUTION_LEASE_LOST,
            CapacityAdmissionPhaseMappingDecision.EXECUTION_LEASE_LOST,
            "ClaimBuilderExecutionLeaseLost",
        ),
        (
            CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED,
            CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED,
            "ClaimBuilderSourceSplitRequired",
        ),
    ),
)
async def test_maps_claim_builder_skipped_results(
    skipped_reason: CapacityWindowAdmissionSkippedReason,
    decision: CapacityAdmissionPhaseMappingDecision,
    event_type: str,
) -> None:
    plan = await ClaimBuilderCapacityAdmissionPhaseMapper().map_admission_result(
        admission_result=_skipped_result(skipped_reason),
        occurred_at=_now(),
    )

    assert plan.decision is decision
    assert plan.workflow_events[0].event_type == event_type
    assert plan.execute_commands == ()
    assert plan.progress_summary is not None
    assert plan.progress_summary.skipped_reason == skipped_reason.value
    assert len(plan.frontend_events) == 1
