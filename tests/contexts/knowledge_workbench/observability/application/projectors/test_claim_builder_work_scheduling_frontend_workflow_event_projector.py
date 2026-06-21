from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_work_scheduling_frontend_workflow_event_projector import (
    ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _event() -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:knowledge-extraction:source-document:project-1:abc:"
            "ClaimBuilderSectionWorkScheduled:source-document:project-1:abc"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_WORK_SCHEDULED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "source_document_ref": "source-document:project-1:abc",
            "scheduled_work_item_count": 2,
        },
        occurred_at=_now(),
        sequence_number=21,
    )


def test_projects_claim_builder_section_work_scheduled_to_versioned_envelope() -> None:
    projected = ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector().project(
        _event()
    )

    assert projected is not None
    assert projected.projection_version == 1
    assert projected.source_sequence_number == 21
    assert projected.projection_type == "workflow_work_items_scheduled"
    assert (
        projected.canonical_phase
        == KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_WORK_SCHEDULING.value
    )
    assert projected.operation_key == "schedule_claim_builder_section_work"
    assert projected.project_id == "project-1"
    assert projected.document_id == "source-document:project-1:abc"
    assert projected.payload == {
        "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
        "source_document_ref": "source-document:project-1:abc",
        "scheduled_work_item_count": 2,
    }


def test_projection_payload_uses_only_canonical_event_fields() -> None:
    projected = ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector().project(
        _event()
    )

    assert projected is not None
    assert set(projected.payload) == {
        "workflow_run_id",
        "source_document_ref",
        "scheduled_work_item_count",
    }


def test_documents_missing_per_item_fields_as_known_limitation() -> None:
    projected = ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector().project(
        _event()
    )

    assert projected is not None
    assert "work_kind" not in projected.payload
    assert "scheduled_items" not in projected.payload
    assert "source_unit_ref" not in projected.payload


def test_ignores_unsupported_workflow_event() -> None:
    projected = ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
            workflow_run_id="workflow-1",
            payload={},
            occurred_at=_now(),
            sequence_number=1,
        )
    )

    assert projected is None


def test_rejects_supported_event_without_source_sequence_number() -> None:
    event = _event()
    unpersisted = WorkflowEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        workflow_run_id=event.workflow_run_id,
        payload=event.payload,
        occurred_at=event.occurred_at,
    )

    with pytest.raises(ValueError, match="sequence_number is required"):
        ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector().project(unpersisted)
