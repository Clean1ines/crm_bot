from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

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
    DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
    CapacityAdmissionPhaseExecuteCommandSummary,
    CapacityAdmissionPhaseMappingDecision,
    CapacityAdmissionPhaseMappingLogEvent,
    CapacityAdmissionPhaseMappingPlan,
    CapacityAdmissionPhaseProgressSummary,
    CapacityAdmissionPhaseWorkflowEventSummary,
)


def _lane(
    *, work_kind: str = "knowledge_workbench.claim_builder.section_extraction"
) -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind=work_kind,
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )


def _admitted_result() -> CapacityWindowAdmissionPassResult:
    lane = _lane()
    projection_event_id = uuid4()
    return CapacityWindowAdmissionPassResult(
        workflow_run_id="workflow-run-1",
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        lane=lane,
        admitted_items=(
            CapacityAdmissionAdmittedItemSummary(
                work_item_id="work-item-1",
                lane=lane,
                selection_kind="fresh",
                estimated_input_tokens=100,
                estimated_output_tokens=40,
                effective_output_cap_tokens=80,
                reserved_total_tokens=180,
            ),
        ),
        projection_leases=(
            CapacityAdmissionProjectionLeaseSummary(
                work_item_id="work-item-1",
                lane=lane,
                previous_status="ready",
                status="leased",
                event_id=projection_event_id,
            ),
        ),
        started_attempts=(
            CapacityAdmissionStartedAttemptSummary(
                attempt_id="work-item-1:attempt:1",
                work_item_id="work-item-1",
                attempt_number=1,
            ),
        ),
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_work_item_admitted",
            workflow_run_id="workflow-run-1",
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
            lane=lane,
            admitted_count=1,
            started_attempt_count=1,
            work_item_ids=("work-item-1",),
            attempt_ids=("work-item-1:attempt:1",),
            projection_event_ids=(projection_event_id,),
            occurred_at=datetime.now(timezone.utc),
        ),
    )


def _skipped_result(
    reason: CapacityWindowAdmissionSkippedReason,
) -> CapacityWindowAdmissionPassResult:
    lane = _lane()
    return CapacityWindowAdmissionPassResult(
        workflow_run_id="workflow-run-1",
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        lane=lane,
        skipped_reason=reason,
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_skipped",
            workflow_run_id="workflow-run-1",
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
            lane=lane,
            admitted_count=0,
            started_attempt_count=0,
            skipped_reason=reason,
            occurred_at=datetime.now(timezone.utc),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
    )


def test_claim_builder_profile_maps_dispatch_prepared_decision_surface() -> None:
    result = _admitted_result()

    plan = CapacityAdmissionPhaseMappingPlan(
        profile=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
        admission_result=result,
        decision=CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED,
        workflow_events=(
            CapacityAdmissionPhaseWorkflowEventSummary(
                event_type=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.dispatch_prepared_event_type,
                event_id="workflow-event:workflow-run-1:claim-builder-prepared",
                workflow_run_id="workflow-run-1",
                work_item_ids=("work-item-1",),
                attempt_ids=("work-item-1:attempt:1",),
                projection_event_ids=(result.projection_leases[0].event_id,),
            ),
        ),
        execute_commands=(
            CapacityAdmissionPhaseExecuteCommandSummary(
                command_type=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.execute_command_type,
                command_ref="workflow-command:execute:work-item-1",
                workflow_run_id="workflow-run-1",
                work_item_id="work-item-1",
                attempt_id="work-item-1:attempt:1",
            ),
        ),
        frontend_events=(result.frontend_event_summary,),
        progress_summary=CapacityAdmissionPhaseProgressSummary(
            workflow_run_id="workflow-run-1",
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            prepared_dispatch_count=1,
            appended_event_count=1,
            appended_next_command_count=1,
        ),
        occurred_at=datetime.now(timezone.utc),
    )

    assert plan.prepared_dispatch_count == 1
    assert plan.appended_next_command_count == 1
    assert (
        plan.log_event is CapacityAdmissionPhaseMappingLogEvent.PHASE_MAPPING_COMPLETED
    )


def test_compaction_profile_is_distinct_and_supports_user_model_choice_decision() -> (
    None
):
    lane = _lane(work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind)
    result = CapacityWindowAdmissionPassResult(
        workflow_run_id="workflow-run-1",
        phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
        operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        lane=lane,
        skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_user_model_choice_required",
            workflow_run_id="workflow-run-1",
            phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
            operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
            lane=lane,
            admitted_count=0,
            started_attempt_count=0,
            skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            occurred_at=datetime.now(timezone.utc),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
    )

    plan = CapacityAdmissionPhaseMappingPlan(
        profile=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
        admission_result=result,
        decision=CapacityAdmissionPhaseMappingDecision.USER_MODEL_CHOICE_REQUIRED,
        frontend_events=(result.frontend_event_summary,),
        progress_summary=CapacityAdmissionPhaseProgressSummary(
            workflow_run_id="workflow-run-1",
            phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
            operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
            prepared_dispatch_count=0,
            appended_event_count=1,
            appended_next_command_count=0,
            skipped_reason="user_model_choice_required",
        ),
        occurred_at=datetime.now(timezone.utc),
        log_event=CapacityAdmissionPhaseMappingLogEvent.PHASE_MAPPING_SKIPPED,
    )

    assert plan.profile.work_kind == "knowledge_workbench.draft_claim_compaction"
    assert plan.profile.supports_user_model_choice_required is True
    assert plan.profile.supports_source_split_required is False


def test_profile_must_match_admission_result_phase_operation_and_work_kind() -> None:
    result = _admitted_result()

    with pytest.raises(ValueError, match="profile phase"):
        CapacityAdmissionPhaseMappingPlan(
            profile=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
            admission_result=result,
            decision=CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED,
            execute_commands=(
                CapacityAdmissionPhaseExecuteCommandSummary(
                    command_type="ExecuteDraftClaimCompaction",
                    command_ref="workflow-command:execute:work-item-1",
                    workflow_run_id="workflow-run-1",
                    work_item_id="work-item-1",
                    attempt_id="work-item-1:attempt:1",
                ),
            ),
        )


def test_claim_builder_profile_supports_source_split_required_decision() -> None:
    result = _skipped_result(CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED)

    plan = CapacityAdmissionPhaseMappingPlan(
        profile=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
        admission_result=result,
        decision=CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED,
        progress_summary=CapacityAdmissionPhaseProgressSummary(
            workflow_run_id="workflow-run-1",
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            prepared_dispatch_count=0,
            appended_event_count=1,
            appended_next_command_count=1,
            skipped_reason="source_split_required",
        ),
        log_event=CapacityAdmissionPhaseMappingLogEvent.PHASE_MAPPING_SKIPPED,
    )

    assert plan.decision is CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED


def test_compaction_profile_rejects_source_split_required_decision() -> None:
    lane = _lane(work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind)
    result = CapacityWindowAdmissionPassResult(
        workflow_run_id="workflow-run-1",
        phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
        operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        lane=lane,
        skipped_reason=CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED,
        log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
    )

    with pytest.raises(ValueError, match="does not support source_split_required"):
        CapacityAdmissionPhaseMappingPlan(
            profile=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
            admission_result=result,
            decision=CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED,
            log_event=CapacityAdmissionPhaseMappingLogEvent.PHASE_MAPPING_SKIPPED,
        )


@pytest.mark.parametrize(
    ("reason", "decision"),
    (
        (
            CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            CapacityAdmissionPhaseMappingDecision.CAPACITY_WAITING,
        ),
        (
            CapacityWindowAdmissionSkippedReason.NO_FITTING_WORK_ITEM,
            CapacityAdmissionPhaseMappingDecision.NO_FITTING_WORK_ITEM,
        ),
        (
            CapacityWindowAdmissionSkippedReason.ACTIVE_LEASED_WAIT,
            CapacityAdmissionPhaseMappingDecision.ACTIVE_LEASED_WAIT,
        ),
        (
            CapacityWindowAdmissionSkippedReason.PROJECTION_CONFLICT,
            CapacityAdmissionPhaseMappingDecision.PROJECTION_CONFLICT,
        ),
        (
            CapacityWindowAdmissionSkippedReason.EXECUTION_LEASE_LOST,
            CapacityAdmissionPhaseMappingDecision.EXECUTION_LEASE_LOST,
        ),
    ),
)
def test_phase_mapping_decision_requires_matching_skipped_reason(
    reason: CapacityWindowAdmissionSkippedReason,
    decision: CapacityAdmissionPhaseMappingDecision,
) -> None:
    plan = CapacityAdmissionPhaseMappingPlan(
        profile=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
        admission_result=_skipped_result(reason),
        decision=decision,
        log_event=CapacityAdmissionPhaseMappingLogEvent.PHASE_MAPPING_SKIPPED,
    )

    assert plan.decision is decision


def test_phase_mapping_source_does_not_import_old_prepare_or_due_scan_contracts() -> (
    None
):
    source = (
        Path("src/contexts/knowledge_workbench/application/sagas/")
        / "capacity_admission_phase_mapping.py"
    ).read_text(encoding="utf-8")

    assert "PrepareLlmDispatchBatch" not in source
    assert "DueWorkItemRecord" not in source
    assert "peek_due_work_items" not in source
    assert "requested_items" not in source
    assert "source_unit_text" not in source
    assert "prompt_text" not in source
    assert "raw_output" not in source
