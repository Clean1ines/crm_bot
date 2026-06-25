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


class DraftClaimCurationFrontendWorkflowEventProjector:
    """Projects curation/review/publication workflow events into frontend patches."""

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
            operation_key="draft_claim_curation",
            canonical_phase=_canonical_phase(event.event_type),
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
    base_patch: dict[str, object] = {
        "workflow_run_id": event.workflow_run_id,
        "project_id": _payload_text(event.payload, "project_id"),
        "source_document_ref": _payload_text(event.payload, "source_document_ref"),
    }

    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_OPENED.value
    ):
        base_patch.update(
            {
                "workspace_ref": _payload_text(event.payload, "workspace_ref"),
                "item_count": _payload_non_negative_int(event.payload, "item_count"),
            }
        )
        return "workflow_draft_claim_curation_workspace_opened", base_patch

    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_REVIEW_REQUIRED.value
    ):
        base_patch.update(
            {
                "workspace_ref": _payload_text(event.payload, "workspace_ref"),
                "item_count": _payload_non_negative_int(event.payload, "item_count"),
            }
        )
        return "workflow_draft_claim_curation_review_required", base_patch

    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value
    ):
        base_patch.update(
            {
                "publication_id": _payload_text(event.payload, "publication_id"),
                "published_item_count": _payload_non_negative_int(
                    event.payload,
                    "published_item_count",
                ),
                "runtime_entry_count": _payload_non_negative_int(
                    event.payload,
                    "runtime_entry_count",
                ),
                "embedding_count": _payload_non_negative_int(
                    event.payload,
                    "embedding_count",
                ),
            }
        )
        return "workflow_draft_claim_curation_workspace_published", base_patch

    raise AssertionError("unsupported event passed the projector allowlist")


def _canonical_phase(event_type: str) -> str:
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value
    ):
        return KnowledgeExtractionCanonicalPhase.PUBLICATION.value
    return KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CURATION.value


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_OPENED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_REVIEW_REQUIRED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value,
    }
)


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"event payload {key} must be non-empty text")
    return value


def _payload_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"event payload {key} must be non-negative int")
    return value
