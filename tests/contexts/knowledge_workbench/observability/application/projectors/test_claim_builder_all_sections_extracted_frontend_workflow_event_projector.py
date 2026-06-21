from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_all_sections_extracted_frontend_workflow_event_projector import (
    ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector,
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
        "completed_count",
        "total_count",
        "claim_count",
        "persisted_claim_count",
        "draft_claim_count",
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


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _summary_payload() -> dict[str, object]:
    return {
        "ready_count": 0,
        "leased_count": 0,
        "deferred_count": 0,
        "retryable_failed_count": 0,
        "completed_count": 3,
        "terminal_failed_count": 0,
        "cancelled_count": 0,
        "split_superseded_count": 0,
        "user_action_required_count": 0,
        "total_count": 3,
        "next_due_at": (_now() + timedelta(minutes=5)).isoformat(),
        "due_deferred_count": 0,
        "due_retryable_failed_count": 0,
    }


def _canonical_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "operation_key": "reconcile_claim_builder_progress",
        "canonical_phase": (
            KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
        ),
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "summary": _summary_payload(),
        "completed_count": 3,
        "total_count": 3,
        "next_command_type": (
            KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS.value
        ),
        "decision": "CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED",
        "next_run_after": (_now() + timedelta(minutes=5)).isoformat(),
        "selected_retry_plan": None,
    }


def _event(*, payload: dict[str, object] | None = None) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{_workflow_run_id()}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED.value}:"
            "workflow-command:reconcile"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED.value
        ),
        workflow_run_id=_workflow_run_id(),
        payload=payload or _canonical_payload(),
        occurred_at=_now(),
        sequence_number=52,
    )


def test_projects_all_sections_extracted_to_versioned_envelope() -> None:
    projected = (
        ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector().project(
            _event()
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_claim_builder_all_sections_extracted"
    assert projected.operation_key == "reconcile_claim_builder_progress"
    assert (
        projected.canonical_phase
        == KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
    )
    assert projected.project_id == "project-1"
    assert projected.document_id == "source-document:project-1:abc"
    assert projected.payload["completed_count"] == 3
    assert projected.payload["total_count"] == 3


def test_ignores_unsupported_workflow_event() -> None:
    projected = ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector().project(
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
        ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector().project(
            _event(payload=payload)
        )


def test_projection_keeps_allowed_top_level_fields_only() -> None:
    projected = (
        ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector().project(
            _event()
        )
    )

    assert projected is not None
    assert set(projected.payload) <= _ALLOWED_TOP_LEVEL_PAYLOAD_KEYS
    assert set(projected.payload) == {
        "workflow_run_id",
        "work_kind",
        "summary",
        "completed_count",
        "total_count",
    }


def test_projection_keeps_allowed_summary_counters_only() -> None:
    projected = (
        ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector().project(
            _event()
        )
    )

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
    projected = (
        ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector().project(
            _event()
        )
    )

    assert projected is not None
    assert forbidden_key not in projected.payload["summary"]


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
    projected = (
        ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector().project(
            _event()
        )
    )

    assert projected is not None
    assert forbidden_key not in projected.payload


def test_projection_does_not_infer_waiting_for_capacity() -> None:
    projected = (
        ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector().project(
            _event()
        )
    )

    assert projected is not None
    assert "waiting_for_capacity" not in projected.payload
    assert "retry_action_summary" not in projected.payload
