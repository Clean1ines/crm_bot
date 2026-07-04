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
from src.domain.project_plane.json_types import JsonValue


PROJECTION_VERSION = 1

_PROJECTION_TYPES = {
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_OPENED.value: (
        "workflow_draft_claim_curation_workspace_opened"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_REVIEW_REQUIRED.value: (
        "workflow_draft_claim_curation_review_required"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value: (
        "workflow_draft_claim_curation_workspace_published"
    ),
}

_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "workflow_run_id",
        "workspace_ref",
        "item_count",
        "excluded_item_count",
        "publication_id",
        "published_item_count",
        "runtime_entry_count",
        "embedding_count",
        "deleted_draft_embedding_count",
    }
)


class DraftClaimCurationFrontendWorkflowEventProjector:
    """Projects curation review/publication events into frontend workflow events."""

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")

        projection_type = _PROJECTION_TYPES.get(event.event_type)
        if projection_type is None:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )

        workflow_run_id = event.workflow_run_id
        project_id, document_id = _document_scope_from_workflow_run_id(workflow_run_id)

        payload = _projection_payload(event.payload)
        payload.setdefault("workflow_run_id", workflow_run_id)
        payload.setdefault("project_id", project_id)
        payload.setdefault("source_document_ref", document_id)

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
            operation_key=_operation_key(event.event_type),
            canonical_phase=_canonical_phase(event.event_type),
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=payload,
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _projection_payload(payload: Mapping[str, object]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key in _ALLOWED_PAYLOAD_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if value is not None:
            result[key] = _json_value(value)
    return result


def _operation_key(event_type: str) -> str:
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value
    ):
        return "publish_draft_claim_curation_workspace"
    return "draft_claim_curation"


def _canonical_phase(event_type: str) -> str:
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value
    ):
        return KnowledgeExtractionCanonicalPhase.PUBLICATION.value
    return KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CURATION.value


def _document_scope_from_workflow_run_id(workflow_run_id: str) -> tuple[str, str]:
    prefix = "knowledge-extraction:source-document:"
    if workflow_run_id.startswith(prefix):
        remainder = workflow_run_id.removeprefix(prefix)
        parts = remainder.split(":", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0], f"source-document:{remainder}"
    return workflow_run_id, workflow_run_id


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return str(value)
