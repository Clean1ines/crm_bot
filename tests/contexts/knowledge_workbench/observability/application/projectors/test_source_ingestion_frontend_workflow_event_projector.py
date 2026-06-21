from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.projectors.source_ingestion_frontend_workflow_event_projector import (
    SourceIngestionFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _event(event_type: KnowledgeExtractionCanonicalEventType) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(f"workflow-event:{event_type.value}"),
        event_type=event_type.value,
        workflow_run_id="workflow-1",
        payload={
            "project_id": "project-1",
            "source_document_ref": "document-1",
            "source_unit_count": 3,
            "source_format": "markdown",
        },
        occurred_at=_now(),
        sequence_number=17,
    )


def test_projects_source_document_persisted_to_versioned_envelope() -> None:
    projected = SourceIngestionFrontendWorkflowEventProjector().project(
        _event(KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED)
    )

    assert projected is not None
    assert projected.projection_version == 1
    assert projected.source_sequence_number == 17
    assert projected.projection_type == "workflow_source_document_persisted"
    assert (
        projected.canonical_phase == KnowledgeExtractionCanonicalPhase.SOURCE_INGESTION
    )
    assert projected.project_id == "project-1"
    assert projected.document_id == "document-1"
    assert projected.payload == {
        "source_document_ref": "document-1",
        "source_format": "markdown",
    }


def test_projects_source_units_created_with_minimal_patch_payload() -> None:
    projected = SourceIngestionFrontendWorkflowEventProjector().project(
        _event(KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED)
    )

    assert projected is not None
    assert projected.projection_type == "workflow_source_units_created"
    assert projected.payload == {
        "source_document_ref": "document-1",
        "source_unit_count": 3,
    }


def test_ignores_unsupported_workflow_event() -> None:
    projected = SourceIngestionFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
            workflow_run_id="workflow-1",
            payload={},
            occurred_at=_now(),
        )
    )

    assert projected is None


def test_rejects_supported_event_without_source_sequence_number() -> None:
    event = _event(KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED)
    unpersisted = WorkflowEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        workflow_run_id=event.workflow_run_id,
        payload=event.payload,
        occurred_at=event.occurred_at,
    )

    with pytest.raises(ValueError, match="sequence_number is required"):
        SourceIngestionFrontendWorkflowEventProjector().project(unpersisted)
