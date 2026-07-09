from __future__ import annotations

from collections.abc import Mapping

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent


PROJECTION_VERSION = 1


class RouteActivationFrontendWorkflowEventProjector:
    """Projects explicit workflow lifecycle/control events for frontend replay."""

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")
        if event.event_type not in _SUPPORTED_EVENT_TYPES:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )

        projection_type, patch = _projection_definition(event)
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
            operation_key="manual_workflow_control",
            canonical_phase="WORKFLOW_CONTROL",
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
    actor_user_id = _payload_text(event.payload, "actor_user_id")
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_PAUSED.value
    ):
        return (
            "workflow_manually_paused",
            {
                "workflow_run_id": event.workflow_run_id,
                "source_document_ref": document_id,
                "actor_user_id": actor_user_id,
                "pause_reason": _payload_text(event.payload, "reason"),
                "document_status": "paused",
                "workflow_status": "paused",
                "timer_mode": "paused",
                "timer_is_live": False,
            },
        )
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_RESUMED.value
    ):
        return (
            "workflow_manually_resumed",
            {
                "workflow_run_id": event.workflow_run_id,
                "source_document_ref": document_id,
                "actor_user_id": actor_user_id,
                "document_status": "processing",
                "workflow_status": "running",
                "timer_mode": "running",
                "timer_is_live": True,
            },
        )
    raise AssertionError("unsupported event passed the projector allowlist")


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_PAUSED.value,
        KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_RESUMED.value,
    }
)


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"event payload {key} must be non-empty text")
    return value
