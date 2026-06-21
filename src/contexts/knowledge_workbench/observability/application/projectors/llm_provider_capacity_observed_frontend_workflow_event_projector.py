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


class LlmProviderCapacityObservedFrontendWorkflowEventProjector:
    """Pure projector for LLM provider capacity observation frontend events."""

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
                f"workflow_capacity_window_observed:v{PROJECTION_VERSION}"
            ),
            source_event_id=event.event_id.value,
            source_sequence_number=event.sequence_number,
            projection_version=PROJECTION_VERSION,
            projection_type="workflow_capacity_window_observed",
            event_type=event.event_type,
            operation_key=operation_key,
            canonical_phase=canonical_phase,
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=_capacity_window_observed_patch(event.payload),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _capacity_window_observed_patch(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    provider = _payload_text(payload, "provider")
    account_ref = _payload_text(payload, "account_ref")
    model_ref = _payload_text(payload, "model_ref")
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "dispatch_attempt_id": _payload_text(payload, "dispatch_attempt_id"),
        "work_item_id": _payload_text(payload, "work_item_id"),
        "window_key": _capacity_window_key(
            provider=provider,
            account_ref=account_ref,
            model_ref=model_ref,
        ),
        "provider": provider,
        "account_ref": account_ref,
        "model_ref": model_ref,
        "outcome_class": _payload_text(payload, "outcome_class"),
        "observed_at": _payload_text(payload, "observed_at"),
    }
    for key in (
        "remaining_minute_requests",
        "remaining_minute_tokens",
        "remaining_daily_requests",
        "remaining_daily_tokens",
        "actual_prompt_tokens",
        "actual_completion_tokens",
        "actual_total_tokens",
    ):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            patch[key] = value
    for key in ("minute_reset_at", "daily_reset_at"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            patch[key] = value
    return patch


def _capacity_window_key(
    *,
    provider: str,
    account_ref: str,
    model_ref: str,
) -> str:
    return f"{provider}:{account_ref}:{model_ref}"


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
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
