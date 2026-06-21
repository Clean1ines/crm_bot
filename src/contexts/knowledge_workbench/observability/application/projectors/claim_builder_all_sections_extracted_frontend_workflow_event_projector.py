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

_ALLOWED_TOP_LEVEL_SCALAR_KEYS = (
    "workflow_run_id",
    "work_kind",
    "completed_count",
    "total_count",
    "claim_count",
    "persisted_claim_count",
    "draft_claim_count",
)

_ALLOWED_SUMMARY_KEYS = frozenset(
    {
        "ready_count",
        "leased_count",
        "retryable_failed_count",
        "completed_count",
        "terminal_failed_count",
        "cancelled_count",
        "split_superseded_count",
        "user_action_required_count",
        "total_count",
    }
)


class ClaimBuilderAllSectionsExtractedFrontendWorkflowEventProjector:
    """Pure projector for claim-builder all-sections-extracted frontend events."""

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
        operation_key = _payload_text(event.payload, "operation_key")
        canonical_phase = _payload_text(event.payload, "canonical_phase")
        return FrontendWorkflowEvent(
            projection_event_id=(
                f"frontend-workflow-event:{event.event_id.value}:"
                f"workflow_claim_builder_all_sections_extracted:v{PROJECTION_VERSION}"
            ),
            source_event_id=event.event_id.value,
            source_sequence_number=event.sequence_number,
            projection_version=PROJECTION_VERSION,
            projection_type="workflow_claim_builder_all_sections_extracted",
            event_type=event.event_type,
            operation_key=operation_key,
            canonical_phase=canonical_phase,
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=_all_sections_extracted_patch(event.payload),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _all_sections_extracted_patch(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {}
    for key in _ALLOWED_TOP_LEVEL_SCALAR_KEYS:
        value = payload.get(key)
        if value is not None:
            patch[key] = value

    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        summary_patch = _allowed_mapping_patch(summary, _ALLOWED_SUMMARY_KEYS)
        if summary_patch:
            patch["summary"] = summary_patch

    return patch


def _allowed_mapping_patch(
    nested: Mapping[str, object],
    allowed_keys: frozenset[str],
) -> dict[str, object]:
    patch: dict[str, object] = {}
    for key in allowed_keys:
        if key not in nested:
            continue
        value = nested[key]
        if value is not None:
            patch[key] = value
    return patch


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED.value,
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
