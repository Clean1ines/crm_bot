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
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.SOURCE_UNIT_CREATED.value
    ):
        patch: dict[str, object] = {
            "workflow_run_id": event.workflow_run_id,
            "source_document_ref": document_id,
            "source_unit_ref": _payload_text(event.payload, "source_unit_ref"),
            "source_unit_ordinal": _payload_non_negative_int(
                event.payload,
                "source_unit_ordinal",
            ),
            "unit_kind": _payload_text(event.payload, "unit_kind"),
            "heading_path": _payload_text_tuple(event.payload, "heading_path"),
        }
        parent_ref = event.payload.get("parent_source_unit_ref")
        if isinstance(parent_ref, str) and parent_ref.strip():
            patch["parent_source_unit_ref"] = parent_ref
        return "workflow_source_unit_created", patch
    raise AssertionError("unsupported event passed the projector allowlist")


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED.value,
        KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
        KnowledgeExtractionCanonicalEventType.SOURCE_UNIT_CREATED.value,
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


def _payload_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"event payload {key} must be non-negative int")
    return value


def _payload_text_tuple(
    payload: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"event payload {key} must be a sequence")
    items = tuple(value)
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"event payload {key} must contain non-empty text")
    return items
