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


class ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector:
    """Pure projector for claim-builder work scheduling frontend events."""

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")
        if event.event_type not in _SUPPORTED_EVENT_TYPES:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )

        source_document_ref = _payload_text(event.payload, "source_document_ref")
        return FrontendWorkflowEvent(
            projection_event_id=(
                f"frontend-workflow-event:{event.event_id.value}:"
                f"workflow_work_items_scheduled:v{PROJECTION_VERSION}"
            ),
            source_event_id=event.event_id.value,
            source_sequence_number=event.sequence_number,
            projection_version=PROJECTION_VERSION,
            projection_type="workflow_work_items_scheduled",
            event_type=event.event_type,
            operation_key="schedule_claim_builder_section_work",
            canonical_phase=(
                KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_WORK_SCHEDULING.value
            ),
            workflow_run_id=event.workflow_run_id,
            project_id=_project_id_from_source_document_ref(source_document_ref),
            document_id=source_document_ref,
            payload=_scheduled_work_items_patch(event.payload),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _scheduled_work_items_patch(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    source_document_ref = _payload_text(payload, "source_document_ref")
    return {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "source_document_ref": source_document_ref,
        "scheduled_work_item_count": _payload_non_negative_int(
            payload,
            "scheduled_work_item_count",
        ),
    }


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_WORK_SCHEDULED.value,
    }
)


def _project_id_from_source_document_ref(source_document_ref: str) -> str:
    parts = source_document_ref.split(":", 2)
    if len(parts) < 3 or parts[0] != "source-document" or not parts[1].strip():
        raise ValueError("source_document_ref must include project_id")
    return parts[1]


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"event payload {key} must be non-empty text")
    return value


def _payload_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"event payload {key} must be int")
    if value < 0:
        raise ValueError(f"event payload {key} must be >= 0")
    return value
