from __future__ import annotations

from collections.abc import Mapping

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent


PROJECTION_VERSION = 1


class SourceIngestionFrontendWorkflowEventProjector:
    """Pure projector skeleton for the first two source-ingestion events."""

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")
        if event.event_type not in _SUPPORTED_EVENT_TYPES:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )

        projection = _projection_definition(event)
        projection_type, patch = projection
        project_id = _payload_text(event.payload, "project_id")
        document_id = _payload_text(event.payload, "source_document_ref")

        return FrontendWorkflowEvent(
            projection_event_id=(
                f"frontend-workflow-event:{event.event_id.value}:"
                f"{projection_type}:v{PROJECTION_VERSION}"
            ),
            source_event_id=event.event_id.value,
            source_sequence_number=event.sequence_number,
            projection_version=PROJECTION_VERSION,
            projection_type=projection_type,
            event_type=event.event_type,
            operation_key="ingest_source_document",
            canonical_phase=KnowledgeExtractionCanonicalPhase.SOURCE_INGESTION.value,
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=patch,
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _projection_definition(
    event: WorkflowEvent,
) -> tuple[str, Mapping[str, object]]:
    document_id = _payload_text(event.payload, "source_document_ref")
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED.value
    ):
        return (
            "workflow_source_document_persisted",
            {
                "source_document_ref": document_id,
                "source_format": _payload_text(event.payload, "source_format"),
            },
        )
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value
    ):
        return (
            "workflow_source_units_created",
            {
                "source_document_ref": document_id,
                "source_unit_count": _payload_positive_int(
                    event.payload,
                    "source_unit_count",
                ),
            },
        )
    raise AssertionError("unsupported event passed the projector allowlist")


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED.value,
        KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
    }
)


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"event payload {key} must be non-empty text")
    return value


def _payload_positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"event payload {key} must be positive int")
    return value
