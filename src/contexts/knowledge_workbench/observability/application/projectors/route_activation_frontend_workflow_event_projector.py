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
    """Projects route activation and work item reroute events into frontend-safe patches."""

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")
        projection_type = _projection_type_for_event_type(event.event_type)
        if projection_type is None:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )

        workflow_run_id = _payload_text(event.payload, "workflow_run_id")
        project_id, document_id = _document_scope_from_workflow_run_id(workflow_run_id)
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
            operation_key=_payload_text(event.payload, "operation_key"),
            canonical_phase=_payload_text(event.payload, "canonical_phase"),
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=_projection_payload(projection_type, event.payload),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _projection_type_for_event_type(event_type: str) -> str | None:
    mapping = {
        KnowledgeExtractionCanonicalEventType.ROUTE_ACTIVATION_CREATED.value: (
            "workflow_route_activation_created"
        ),
        KnowledgeExtractionCanonicalEventType.ROUTE_ACTIVATION_CLOSED.value: (
            "workflow_route_activation_closed"
        ),
        KnowledgeExtractionCanonicalEventType.WORK_ITEM_REROUTE_REQUESTED.value: (
            "workflow_work_item_reroute_requested"
        ),
        KnowledgeExtractionCanonicalEventType.WORK_ITEM_REROUTED.value: (
            "workflow_work_item_rerouted"
        ),
        KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_PAUSED.value: (
            "workflow_manually_paused"
        ),
        KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_RESUMED.value: (
            "workflow_manually_resumed"
        ),
    }
    return mapping.get(event_type)


def _projection_payload(
    projection_type: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    if projection_type in {
        "workflow_route_activation_created",
        "workflow_route_activation_closed",
    }:
        return _route_activation_payload(payload)
    if projection_type in {
        "workflow_work_item_reroute_requested",
        "workflow_work_item_rerouted",
    }:
        return _work_item_reroute_payload(payload)
    if projection_type in {
        "workflow_manually_paused",
        "workflow_manually_resumed",
    }:
        return _manual_transition_payload(projection_type, payload)
    raise ValueError(f"unsupported route projection type: {projection_type}")


def _route_activation_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "canonical_phase": _payload_text(payload, "canonical_phase"),
        "operation_key": _payload_text(payload, "operation_key"),
        "route_activation_ref": _payload_text(payload, "route_activation_ref"),
        "work_kind": _payload_text(payload, "work_kind"),
        "provider": _payload_text(payload, "provider"),
        "model_ref": _payload_text(payload, "model_ref"),
        "route_kind": _payload_text(payload, "route_kind"),
        "route_reason": _payload_text(payload, "route_reason"),
        "activation_scope": _payload_text(payload, "activation_scope"),
        "status": _payload_text(payload, "status"),
    }
    _copy_optional_text(payload, patch, "target_work_item_id")
    _copy_optional_text(payload, patch, "causation_command_id")
    return patch


def _work_item_reroute_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "canonical_phase": _payload_text(payload, "canonical_phase"),
        "operation_key": _payload_text(payload, "operation_key"),
        "work_item_id": _payload_text(payload, "work_item_id"),
        "work_kind": _payload_text(payload, "work_kind"),
        "previous_route_activation_ref": _payload_text(
            payload,
            "previous_route_activation_ref",
        ),
        "next_route_activation_ref": _payload_text(
            payload,
            "next_route_activation_ref",
        ),
        "route_reason": _payload_text(payload, "route_reason"),
    }
    for key in (
        "source_unit_ref",
        "previous_model_ref",
        "next_model_ref",
        "causation_command_id",
    ):
        _copy_optional_text(payload, patch, key)
    for key in ("estimated_input_tokens", "reserved_total_tokens"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            patch[key] = value
    return patch


def _manual_transition_payload(
    projection_type: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "project_id": _payload_text(payload, "project_id"),
        "source_document_ref": _payload_text(payload, "source_document_ref"),
        "status": "paused"
        if projection_type == "workflow_manually_paused"
        else "running",
    }
    _copy_optional_text(payload, patch, "actor_user_id")
    _copy_optional_text(payload, patch, "reason")
    return patch


def _copy_optional_text(
    source: Mapping[str, object],
    target: dict[str, object],
    key: str,
) -> None:
    value = source.get(key)
    if isinstance(value, str) and value.strip():
        target[key] = value


def _document_scope_from_workflow_run_id(workflow_run_id: str) -> tuple[str, str]:
    prefix = "knowledge-extraction:source-document:"
    if workflow_run_id.startswith(prefix):
        remainder = workflow_run_id.removeprefix(prefix)
        parts = remainder.split(":", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0], f"source-document:{remainder}"
    return workflow_run_id, workflow_run_id


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"event payload {key} must be non-empty text")
    return value
