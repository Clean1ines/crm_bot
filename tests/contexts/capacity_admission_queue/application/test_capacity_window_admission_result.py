from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionAdmittedItemSummary,
    CapacityAdmissionDispatchContextSummary,
    CapacityAdmissionFrontendEventSummary,
    CapacityAdmissionLaneSummary,
    CapacityAdmissionProjectionLeaseSummary,
    CapacityAdmissionSafePreflightSummary,
    CapacityAdmissionStartedAttemptSummary,
    CapacityWindowAdmissionLogEvent,
    CapacityWindowAdmissionPassResult,
    CapacityWindowAdmissionSkippedReason,
)


def _lane() -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )


def _context() -> CapacityAdmissionDispatchContextSummary:
    return CapacityAdmissionDispatchContextSummary(
        source_unit_ref="source-unit-1",
        group_ref="group-1",
        batch_ref="batch-1",
        round_index=0,
        expected_output_kind="claim_observations",
        input_node_refs=("node-1",),
        input_claim_refs=("claim-1",),
    )


def _admitted_item() -> CapacityAdmissionAdmittedItemSummary:
    return CapacityAdmissionAdmittedItemSummary(
        work_item_id="work-item-1",
        lane=_lane(),
        selection_kind="fresh",
        input_tokens=100,
        artifact_tokens=40,
        required_window_tokens=180,
        dispatch_context=_context(),
    )


def _projection_lease(
    event_id: UUID | None = None,
) -> CapacityAdmissionProjectionLeaseSummary:
    return CapacityAdmissionProjectionLeaseSummary(
        work_item_id="work-item-1",
        lane=_lane(),
        previous_status="ready",
        status="leased",
        event_id=event_id or uuid4(),
    )


def _started_attempt() -> CapacityAdmissionStartedAttemptSummary:
    return CapacityAdmissionStartedAttemptSummary(
        attempt_id="work-item-1:attempt:1",
        work_item_id="work-item-1",
        attempt_number=1,
    )


def _preflight_summary() -> CapacityAdmissionSafePreflightSummary:
    return CapacityAdmissionSafePreflightSummary(
        decision="USE_ACTIVE_MODEL",
        reason="input size preflight used active model",
        active_model_ref="qwen/qwen3-32b",
    )


def _frontend_summary(
    *,
    projection_event_id: UUID,
) -> CapacityAdmissionFrontendEventSummary:
    return CapacityAdmissionFrontendEventSummary(
        event_kind="capacity_admission_work_item_admitted",
        workflow_run_id="workflow-run-1",
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        operation_key="prepare_claim_builder_dispatch",
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        lane=_lane(),
        admitted_count=1,
        started_attempt_count=1,
        work_item_ids=("work-item-1",),
        attempt_ids=("work-item-1:attempt:1",),
        projection_event_ids=(projection_event_id,),
        dispatch_contexts=(_context(),),
        occurred_at=datetime.now(timezone.utc),
    )


def test_admitted_result_accepts_safe_generic_capacity_admission_contract() -> None:
    projection_event_id = uuid4()

    result = CapacityWindowAdmissionPassResult(
        workflow_run_id="workflow-run-1",
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        operation_key="prepare_claim_builder_dispatch",
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        lane=_lane(),
        admitted_items=(_admitted_item(),),
        projection_leases=(_projection_lease(projection_event_id),),
        started_attempts=(_started_attempt(),),
        safe_preflight_summary=_preflight_summary(),
        frontend_event_summary=_frontend_summary(
            projection_event_id=projection_event_id,
        ),
    )

    assert result.admitted_count == 1
    assert result.started_attempt_count == 1
    assert result.skipped is False
    assert result.skipped_reason is None
    assert result.log_event is CapacityWindowAdmissionLogEvent.PASS_COMPLETED


@pytest.mark.parametrize(
    "reason",
    tuple(CapacityWindowAdmissionSkippedReason),
)
def test_skipped_result_accepts_closed_skipped_reason_set(
    reason: CapacityWindowAdmissionSkippedReason,
) -> None:
    result = CapacityWindowAdmissionPassResult(
        workflow_run_id="workflow-run-1",
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        operation_key="prepare_claim_builder_dispatch",
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        lane=_lane(),
        skipped_reason=reason,
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_skipped",
            workflow_run_id="workflow-run-1",
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            operation_key="prepare_claim_builder_dispatch",
            work_kind="knowledge_workbench.claim_builder.section_extraction",
            lane=_lane(),
            admitted_count=0,
            started_attempt_count=0,
            skipped_reason=reason,
            occurred_at=datetime.now(timezone.utc),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
    )

    assert result.skipped is True
    assert result.admitted_count == 0
    assert result.started_attempt_count == 0


def test_admitted_result_rejects_missing_execution_reference() -> None:
    with pytest.raises(
        ValueError,
        match="started_attempts or appended_execute_command_refs",
    ):
        CapacityWindowAdmissionPassResult(
            workflow_run_id="workflow-run-1",
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            operation_key="prepare_claim_builder_dispatch",
            work_kind="knowledge_workbench.claim_builder.section_extraction",
            lane=_lane(),
            admitted_items=(_admitted_item(),),
            projection_leases=(_projection_lease(),),
        )


def test_admitted_result_rejects_projection_lease_mismatch() -> None:
    wrong_lease = CapacityAdmissionProjectionLeaseSummary(
        work_item_id="different-work-item",
        lane=_lane(),
        previous_status="ready",
        status="leased",
        event_id=uuid4(),
    )

    with pytest.raises(ValueError, match="same work items"):
        CapacityWindowAdmissionPassResult(
            workflow_run_id="workflow-run-1",
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            operation_key="prepare_claim_builder_dispatch",
            work_kind="knowledge_workbench.claim_builder.section_extraction",
            lane=_lane(),
            admitted_items=(_admitted_item(),),
            projection_leases=(wrong_lease,),
            started_attempts=(_started_attempt(),),
        )


def test_skipped_result_rejects_admitted_items() -> None:
    with pytest.raises(
        ValueError, match="skipped result must not include admitted_items"
    ):
        CapacityWindowAdmissionPassResult(
            workflow_run_id="workflow-run-1",
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            operation_key="prepare_claim_builder_dispatch",
            work_kind="knowledge_workbench.claim_builder.section_extraction",
            lane=_lane(),
            admitted_items=(_admitted_item(),),
            skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
        )


def test_source_split_preflight_summary_requires_source_unit_refs() -> None:
    with pytest.raises(ValueError, match="source_unit_refs"):
        CapacityAdmissionSafePreflightSummary(
            decision="SOURCE_SPLIT_REQUIRED",
            reason="source unit exceeds active model context",
            active_model_ref="qwen/qwen3-32b",
            source_split_required=True,
        )
