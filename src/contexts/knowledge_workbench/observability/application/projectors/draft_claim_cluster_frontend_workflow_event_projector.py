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

_EXPECTED_OPERATION_KEY = "cluster_draft_claims"
_EXPECTED_CANONICAL_PHASE = (
    KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
)

_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "workflow_run_id",
        "candidate_edge_count",
        "group_count",
        "batch_count",
        "scheduled_work_item_count",
        "semantic_meaning",
    }
)

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "operation_key",
        "canonical_phase",
        "run_after",
        "next_run_after",
        "next_due_at",
        "capacity_retry_at",
        "claim_builder_next_run_after",
        "provider_wait_until",
        "quota_reset_at",
        "minute_reset_at",
        "daily_reset_at",
        "next_command_type",
        "decision",
        "selected_retry_plan",
    }
)


class DraftClaimClusterFrontendWorkflowEventProjector:
    """Pure projector for draft-claim clustering frontend events."""

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")
        if event.event_type not in _SUPPORTED_EVENT_TYPES:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )

        workflow_run_id = _payload_text(event.payload, "workflow_run_id")
        project_id, document_id = _document_scope_from_workflow_run_id(workflow_run_id)
        operation_key = _expected_payload_text(
            event.payload,
            "operation_key",
            expected=_EXPECTED_OPERATION_KEY,
        )
        canonical_phase = _expected_payload_text(
            event.payload,
            "canonical_phase",
            expected=_EXPECTED_CANONICAL_PHASE,
        )
        return FrontendWorkflowEvent(
            projection_event_id=(
                f"frontend-workflow-event:{event.event_id.value}:"
                f"workflow_draft_claim_clusters_built:v{PROJECTION_VERSION}"
            ),
            source_event_id=event.event_id.value,
            source_sequence_number=event.sequence_number,
            projection_version=PROJECTION_VERSION,
            projection_type="workflow_draft_claim_clusters_built",
            event_type=event.event_type,
            operation_key=operation_key,
            canonical_phase=canonical_phase,
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=_clusters_built_patch(event.payload),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _clusters_built_patch(payload: Mapping[str, object]) -> dict[str, object]:
    patch: dict[str, object] = {}
    for key in _ALLOWED_PAYLOAD_KEYS:
        if key in _FORBIDDEN_PAYLOAD_KEYS:
            continue
        if key not in payload:
            continue
        value = payload[key]
        if value is not None:
            patch[key] = value
    return patch


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
    }
)


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


def _expected_payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    expected: str,
) -> str:
    value = _payload_text(payload, key)
    if value != expected:
        raise ValueError(f"event payload {key} must be {expected}")
    return value
