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

_EVENT_PROJECTION_TYPES: dict[str, str] = {
    KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value: (
        "workflow_claim_builder_section_extracted"
    ),
    KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value: (
        "workflow_claim_builder_section_retryable_failed"
    ),
    KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED.value: (
        "workflow_claim_builder_section_terminal_failed"
    ),
}


class ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector:
    """Pure projector for claim-builder section execution outcome frontend events."""

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")
        projection_type = _EVENT_PROJECTION_TYPES.get(event.event_type)
        if projection_type is None:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )
        if (
            event.event_type
            == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            and _is_capacity_owned_retryable_failure(event.payload)
        ):
            return None

        workflow_run_id = _payload_text(event.payload, "workflow_run_id")
        project_id, document_id = _document_scope_from_workflow_run_id(workflow_run_id)
        operation_key = _payload_text(event.payload, "operation_key")
        canonical_phase = _payload_text(event.payload, "canonical_phase")
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
            operation_key=operation_key,
            canonical_phase=canonical_phase,
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=_outcome_patch(event.event_type, event.payload),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _outcome_patch(
    event_type: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value
    ):
        return _extracted_patch(payload)
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
    ):
        return _retryable_failed_patch(payload)
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED.value
    ):
        return _terminal_failed_patch(payload)
    raise ValueError(f"unsupported outcome event type: {event_type}")


def _extracted_patch(payload: Mapping[str, object]) -> Mapping[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    source_document_ref = _payload_text(payload, "source_document_ref")
    source_unit_ref = _payload_text(payload, "source_unit_ref")
    work_item_id = _payload_text(payload, "work_item_id")
    dispatch_attempt_id = _payload_text(payload, "dispatch_attempt_id")
    persisted_count = _payload_non_negative_int(
        payload,
        "persisted_draft_claim_count",
    )
    patch: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "source_document_ref": source_document_ref,
        "source_unit_ref": source_unit_ref,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        "source_unit_claim_builder_status": "completed",
        "work_item_state": "completed",
        "dispatch_attempt_state": "completed",
        "persisted_draft_claim_count": persisted_count,
        "draft_claims_available": True,
        "draft_claims_count": persisted_count,
        "draft_claims_scope": {
            "workflow_run_id": workflow_run_id,
            "source_document_ref": source_document_ref,
            "source_unit_ref": source_unit_ref,
            "work_item_id": work_item_id,
            "dispatch_attempt_id": dispatch_attempt_id,
        },
        "targeted_read_kind": "draft_claims_by_work_item_or_source_unit",
    }
    validated_claim_count = _optional_payload_int(payload, "validated_claim_count")
    if validated_claim_count is not None:
        patch["validated_claim_count"] = validated_claim_count
    for key in ("provider", "account_ref", "model_ref"):
        value = _optional_payload_text(payload, key)
        if value is not None:
            patch[key] = value
    for token_key in (
        "actual_prompt_tokens",
        "actual_completion_tokens",
        "actual_total_tokens",
    ):
        token_value = payload.get(token_key)
        if isinstance(token_value, int) and not isinstance(token_value, bool):
            patch[token_key] = token_value
    for key in (
        "validation_decision",
        "claim_builder_attempt_outcome_kind",
        "claim_builder_attempt_next_action_kind",
    ):
        value = _optional_payload_text(payload, key)
        if value is not None:
            patch[key] = value
    return patch


def _retryable_failed_patch(payload: Mapping[str, object]) -> Mapping[str, object]:
    patch = dict(_failure_patch(payload))
    patch.update(
        {
            "source_unit_claim_builder_status": "retryable",
            "work_item_state": "retryable_failed",
            "dispatch_attempt_state": "retryable_failed",
            "retry_eligibility": "eligible_for_future_admission",
            "retry_driver": "capacity_window_admission",
            "failure_reason_category": _failure_reason_category(payload),
        }
    )
    for key in (
        "claim_builder_attempt_next_action_kind",
        "claim_builder_attempt_next_action_reason",
        "claim_builder_attempt_outcome_kind",
    ):
        value = _optional_payload_text(payload, key)
        if value is not None:
            patch[key] = value
    retry_recommended = payload.get("retry_recommended")
    if isinstance(retry_recommended, bool):
        patch["retry_recommended"] = retry_recommended
    return patch


def _terminal_failed_patch(payload: Mapping[str, object]) -> Mapping[str, object]:
    patch = dict(_failure_patch(payload))
    reason_category = _failure_reason_category(payload)
    patch.update(
        {
            "source_unit_claim_builder_status": "terminal_failed",
            "work_item_state": "terminal_failed",
            "dispatch_attempt_state": "terminal_failed",
            "retry_eligibility": "not_eligible",
            "failure_reason_category": reason_category,
            "terminal_reason_category": reason_category,
        }
    )
    for key in (
        "claim_builder_attempt_next_action_kind",
        "claim_builder_attempt_next_action_reason",
        "claim_builder_attempt_outcome_kind",
    ):
        value = _optional_payload_text(payload, key)
        if value is not None:
            patch[key] = value
    return patch


def _failure_patch(payload: Mapping[str, object]) -> dict[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "source_document_ref": _payload_text(payload, "source_document_ref"),
        "source_unit_ref": _payload_text(payload, "source_unit_ref"),
        "dispatch_attempt_id": _payload_text(payload, "dispatch_attempt_id"),
        "work_item_id": _payload_text(payload, "work_item_id"),
    }
    for key in ("error_kind", "validation_failure_reason"):
        value = _optional_payload_text(payload, key)
        if value is not None:
            patch[key] = value
    attempt_number = _optional_payload_int(payload, "attempt_number")
    if attempt_number is not None:
        patch["attempt_number"] = attempt_number
    return patch


def _failure_reason_category(payload: Mapping[str, object]) -> str:
    if _optional_payload_text(payload, "validation_failure_reason") is not None:
        return "validation"
    error_kind = _optional_payload_text(payload, "error_kind")
    if error_kind in {
        "provider_error",
        "auth_error",
        "request_too_large",
        "output_too_large",
    }:
        return "provider_execution"
    if error_kind is not None and "persist" in error_kind:
        return "persistence"
    return "workflow_policy"


_CAPACITY_OWNED_RETRY_ACTION_KINDS = frozenset(
    {
        "DEFER_UNTIL_CAPACITY_RESET",
        "PAUSE_FOR_DAILY_LIMIT_RESET",
    }
)


def _is_capacity_owned_retryable_failure(payload: Mapping[str, object]) -> bool:
    action_kind = _optional_payload_text(
        payload,
        "claim_builder_attempt_next_action_kind",
    )
    return action_kind in _CAPACITY_OWNED_RETRY_ACTION_KINDS


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


def _optional_payload_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _optional_payload_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value


def _payload_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"event payload {key} must be int")
    if value < 0:
        raise ValueError(f"event payload {key} must be >= 0")
    return value
