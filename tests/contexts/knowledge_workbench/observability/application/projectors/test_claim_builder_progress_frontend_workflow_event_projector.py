from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_progress_frontend_workflow_event_projector import (
    ClaimBuilderProgressFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)

_ALLOWED_TOP_LEVEL_PAYLOAD_KEYS = frozenset(
    {
        "workflow_run_id",
        "work_kind",
        "summary",
        "retry_action_summary",
    }
)

_ALLOWED_SUMMARY_KEYS = frozenset(
    {
        "ready_count",
        "leased_count",
        "retryable_failed_count",
        "completed_count",
        "terminal_failed_count",
        "cancelled_count",
        "split_superseded_count",
        "user_action_required_count",
        "total_count",
    }
)

_ALLOWED_RETRY_ACTION_SUMMARY_KEYS = frozenset(
    {
        "workflow_run_id",
        "work_kind",
        "retry_same_route_count",
        "retry_empty_claims_check_model_count",
        "retry_fallback_model_count",
        "retry_larger_output_limit_route_count",
        "retry_larger_input_model_count",
        "split_required_count",
        "request_user_low_quality_continue_or_wait_count",
    }
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _summary_payload() -> dict[str, object]:
    return {
        "ready_count": 1,
        "leased_count": 0,
        "deferred_count": 0,
        "retryable_failed_count": 1,
        "completed_count": 2,
        "terminal_failed_count": 0,
        "cancelled_count": 0,
        "split_superseded_count": 0,
        "user_action_required_count": 0,
        "total_count": 4,
        "next_due_at": (_now() + timedelta(minutes=5)).isoformat(),
        "due_deferred_count": 0,
        "due_retryable_failed_count": 1,
    }


def _retry_action_summary_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "retry_same_route_count": 0,
        "retry_empty_claims_check_model_count": 0,
        "retry_fallback_model_count": 1,
        "retry_larger_output_limit_route_count": 0,
        "retry_larger_input_model_count": 0,
        "split_required_count": 0,
        "defer_until_capacity_reset_count": 1,
        "pause_for_daily_limit_reset_count": 0,
        "request_user_low_quality_continue_or_wait_count": 0,
        "next_run_after": (_now() + timedelta(minutes=5)).isoformat(),
        "selected_retry_plan": None,
    }


def _canonical_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "operation_key": "reconcile_claim_builder_progress",
        "canonical_phase": (
            KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
        ),
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "decision": "PREPARE_NEXT_BATCH_LATER",
        "summary": _summary_payload(),
        "retry_action_summary": _retry_action_summary_payload(),
        "selected_retry_plan": None,
        "next_command_type": "PrepareClaimBuilderDispatchBatch",
        "next_run_after": (_now() + timedelta(minutes=5)).isoformat(),
    }


def _event(*, payload: dict[str, object] | None = None) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{_workflow_run_id()}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_PROGRESS_RECONCILED.value}:"
            "workflow-command:reconcile"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_PROGRESS_RECONCILED.value
        ),
        workflow_run_id=_workflow_run_id(),
        payload=payload or _canonical_payload(),
        occurred_at=_now(),
        sequence_number=51,
    )


def test_projects_progress_reconciled_to_versioned_envelope() -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(_event())

    assert projected is not None
    assert projected.projection_type == "workflow_claim_builder_progress_reconciled"
    assert projected.operation_key == "reconcile_claim_builder_progress"
    assert (
        projected.canonical_phase
        == KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
    )
    assert projected.project_id == "project-1"
    assert projected.document_id == "source-document:project-1:abc"
    assert projected.payload["summary"]["total_count"] == 4
    assert projected.payload["retry_action_summary"]["retry_fallback_model_count"] == 1


def test_ignores_unsupported_workflow_event() -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
            workflow_run_id=_workflow_run_id(),
            payload={"workflow_run_id": _workflow_run_id()},
            occurred_at=_now(),
            sequence_number=1,
        )
    )

    assert projected is None


@pytest.mark.parametrize("missing_key", ("operation_key", "canonical_phase"))
def test_requires_explicit_envelope_fields_in_payload(missing_key: str) -> None:
    payload = _canonical_payload()
    del payload[missing_key]

    with pytest.raises(ValueError, match=missing_key):
        ClaimBuilderProgressFrontendWorkflowEventProjector().project(
            _event(payload=payload)
        )


def test_projection_keeps_allowed_top_level_fields_only() -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(_event())

    assert projected is not None
    assert set(projected.payload) <= _ALLOWED_TOP_LEVEL_PAYLOAD_KEYS
    assert set(projected.payload) == {
        "workflow_run_id",
        "work_kind",
        "summary",
        "retry_action_summary",
    }


def test_projection_keeps_allowed_summary_counters_only() -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(_event())

    assert projected is not None
    assert set(projected.payload["summary"]) == _ALLOWED_SUMMARY_KEYS


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "deferred_count",
        "due_deferred_count",
        "next_due_at",
        "due_retryable_failed_count",
    ),
)
def test_projection_drops_forbidden_summary_field(forbidden_key: str) -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(_event())

    assert projected is not None
    assert forbidden_key not in projected.payload["summary"]


def test_projection_keeps_item_owned_retry_action_summary_counts() -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(_event())

    assert projected is not None
    assert (
        set(projected.payload["retry_action_summary"])
        == _ALLOWED_RETRY_ACTION_SUMMARY_KEYS
    )
    assert projected.payload["retry_action_summary"]["retry_fallback_model_count"] == 1


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "defer_until_capacity_reset_count",
        "pause_for_daily_limit_reset_count",
        "next_run_after",
        "selected_retry_plan",
    ),
)
def test_projection_drops_forbidden_retry_action_summary_field(
    forbidden_key: str,
) -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(_event())

    assert projected is not None
    assert forbidden_key not in projected.payload["retry_action_summary"]


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "decision",
        "selected_retry_plan",
        "next_command_type",
        "next_run_after",
        "operation_key",
        "canonical_phase",
    ),
)
def test_projection_drops_forbidden_top_level_field(forbidden_key: str) -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(_event())

    assert projected is not None
    assert forbidden_key not in projected.payload


def test_projection_does_not_infer_waiting_for_capacity() -> None:
    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(_event())

    assert projected is not None
    assert "waiting_for_capacity" not in projected.payload
    assert "progress_percent" not in projected.payload
    assert "queued_count" not in projected.payload


def test_projection_omits_empty_retry_action_summary_after_filter() -> None:
    payload = _canonical_payload()
    payload["retry_action_summary"] = {
        "defer_until_capacity_reset_count": 2,
        "pause_for_daily_limit_reset_count": 1,
        "next_run_after": (_now() + timedelta(minutes=5)).isoformat(),
        "selected_retry_plan": None,
    }

    projected = ClaimBuilderProgressFrontendWorkflowEventProjector().project(
        _event(payload=payload)
    )

    assert projected is not None
    assert "retry_action_summary" not in projected.payload
