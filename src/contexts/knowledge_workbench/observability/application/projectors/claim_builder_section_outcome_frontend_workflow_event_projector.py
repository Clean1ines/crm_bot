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
    draft_claim_observation_rows = _draft_claim_observation_rows_patch(
        payload,
        row_count=persisted_count,
    )
    draft_claims_available = draft_claim_observation_rows is not None
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
        "draft_claims_available": draft_claims_available,
        "draft_claims_count": persisted_count,
        "draft_claims_scope": {
            "workflow_run_id": workflow_run_id,
            "source_document_ref": source_document_ref,
            "source_unit_ref": source_unit_ref,
            "work_item_id": work_item_id,
            "dispatch_attempt_id": dispatch_attempt_id,
        },
    }
    if draft_claim_observation_rows is not None:
        patch["draft_claim_observation_rows"] = draft_claim_observation_rows
        patch["targeted_read_kind"] = "draft_claims_by_work_item_or_source_unit"
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
    patch["attempt_outcome"] = _attempt_outcome_patch("completed", payload)
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
    patch["attempt_outcome"] = _attempt_outcome_patch("retryable", payload)
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
    patch["attempt_outcome"] = _attempt_outcome_patch("terminal_failed", payload)
    return patch


def _draft_claim_observation_rows_patch(
    payload: Mapping[str, object],
    *,
    row_count: int,
) -> Mapping[str, object] | None:
    if row_count <= 0 or _valid_empty_accepted(payload):
        return None
    return {
        "surface_kind": "draft_claim_observation",
        "availability": "available",
        "row_count": row_count,
        "parent_scope": {
            "workflow_run_id": _payload_text(payload, "workflow_run_id"),
            "source_document_ref": _payload_text(payload, "source_document_ref"),
            "source_unit_ref": _payload_text(payload, "source_unit_ref"),
            "work_item_id": _payload_text(payload, "work_item_id"),
            "dispatch_attempt_id": _payload_text(payload, "dispatch_attempt_id"),
        },
        "targeted_read": {
            "kind": "draft_claims_by_work_item_or_source_unit",
            "params": _draft_claims_scope_patch(payload),
        },
    }


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


def _attempt_outcome_patch(
    final_work_item_status: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    return {
        "attempt_scope": _attempt_scope_patch(payload),
        "provider_outcome": _provider_outcome_patch(final_work_item_status, payload),
        "validation_outcome": _validation_outcome_patch(
            final_work_item_status,
            payload,
        ),
        "persistence_outcome": _persistence_outcome_patch(
            final_work_item_status,
            payload,
        ),
        "work_item_outcome": _work_item_outcome_patch(
            final_work_item_status,
            payload,
        ),
        "capacity_annotation": _capacity_annotation_patch(payload),
        "targeted_read_hint": _targeted_read_hint_patch(
            final_work_item_status,
            payload,
        ),
    }


def _attempt_scope_patch(payload: Mapping[str, object]) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "source_document_ref": _payload_text(payload, "source_document_ref"),
        "source_unit_ref": _payload_text(payload, "source_unit_ref"),
        "work_item_id": _payload_text(payload, "work_item_id"),
        "dispatch_attempt_id": _payload_text(payload, "dispatch_attempt_id"),
    }
    for key in ("operation_key", "canonical_phase"):
        value = _optional_payload_text(payload, key)
        if value is not None:
            patch[key] = value
    return patch


def _provider_outcome_patch(
    final_work_item_status: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    provider_status = _provider_status(final_work_item_status, payload)
    patch: dict[str, object] = {"provider_status": provider_status}
    if provider_status in {"failed", "rate_limited"}:
        error_kind = _optional_payload_text(payload, "error_kind")
        if error_kind is not None:
            patch["provider_error_kind"] = error_kind
    for key in ("provider", "account_ref", "model_ref"):
        value = _optional_payload_text(payload, key)
        if value is not None:
            patch[key] = value
    for token_key in (
        "actual_prompt_tokens",
        "actual_completion_tokens",
        "actual_total_tokens",
    ):
        token_value = _optional_payload_int(payload, token_key)
        if token_value is not None:
            patch[token_key] = token_value
    return patch


def _provider_status(
    final_work_item_status: str,
    payload: Mapping[str, object],
) -> str:
    if _is_capacity_owned_retryable_failure(payload):
        return "rate_limited"
    validation_failure_reason = _optional_payload_text(
        payload,
        "validation_failure_reason",
    )
    if final_work_item_status == "completed" or validation_failure_reason is not None:
        return "succeeded"
    error_kind = _optional_payload_text(payload, "error_kind")
    if error_kind is None:
        return "unknown"
    if error_kind in {"minute_limit", "daily_limit"}:
        return "rate_limited"
    if error_kind in {
        "auth_error",
        "network_error",
        "provider_error",
        "request_too_large",
        "output_too_large",
        "unknown",
    }:
        return "failed"
    if "provider" in error_kind or "network" in error_kind:
        return "failed"
    if "timeout" in error_kind or "auth" in error_kind:
        return "failed"
    if "too_large" in error_kind:
        return "failed"
    return "unknown"


def _validation_outcome_patch(
    final_work_item_status: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "validation_status": _validation_status(final_work_item_status, payload),
        "valid_empty_accepted": _valid_empty_accepted(payload),
    }
    for source_key, target_key in (
        ("validation_decision", "validation_decision"),
        ("validation_failure_reason", "validation_failure_reason"),
        ("claim_builder_attempt_next_action_kind", "validation_next_action"),
    ):
        value = _optional_payload_text(payload, source_key)
        if value is not None:
            patch[target_key] = value
    validated_claim_count = _optional_payload_int(payload, "validated_claim_count")
    if validated_claim_count is not None:
        patch["validated_claim_count"] = validated_claim_count
    output_truncated = _output_truncated(payload)
    if output_truncated is not None:
        patch["output_truncated"] = output_truncated
    return patch


def _validation_status(
    final_work_item_status: str,
    payload: Mapping[str, object],
) -> str:
    if _valid_empty_accepted(payload):
        return "passed_valid_empty"
    validation_decision = _optional_payload_text(payload, "validation_decision")
    validated_claim_count = _optional_payload_int(payload, "validated_claim_count")
    if final_work_item_status == "completed":
        if validation_decision == "VALID_CLAIMS":
            return "passed_valid_claims"
        if validated_claim_count is not None and validated_claim_count > 0:
            return "passed_valid_claims"
        return "unknown"
    if _optional_payload_text(payload, "validation_failure_reason") is None:
        return "not_run"
    if final_work_item_status == "terminal_failed":
        return "failed_terminal"
    return "failed_retryable"


def _valid_empty_accepted(payload: Mapping[str, object]) -> bool:
    validation_decision = _optional_payload_text(payload, "validation_decision")
    next_action = _optional_payload_text(
        payload,
        "claim_builder_attempt_next_action_kind",
    )
    return validation_decision == "VALID_EMPTY" or next_action == "ACCEPT_VALID_EMPTY"


def _output_truncated(payload: Mapping[str, object]) -> bool | None:
    raw_value = payload.get("output_truncated")
    if isinstance(raw_value, bool):
        return raw_value
    next_action = _optional_payload_text(
        payload,
        "claim_builder_attempt_next_action_kind",
    )
    if next_action == "RETRY_LARGER_OUTPUT_LIMIT_MODEL":
        return True
    error_kind = _optional_payload_text(payload, "error_kind")
    if error_kind == "output_too_large":
        return True
    return None


def _persistence_outcome_patch(
    final_work_item_status: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    persisted_count = _optional_payload_int(payload, "persisted_draft_claim_count")
    if final_work_item_status != "completed":
        return {
            "persistence_status": "not_applicable",
            "persisted_draft_claim_count": persisted_count or 0,
            "draft_claims_available": False,
        }
    if _valid_empty_accepted(payload):
        return {
            "persistence_status": "skipped",
            "persisted_draft_claim_count": 0,
            "draft_claims_available": False,
        }
    if persisted_count is not None and persisted_count > 0:
        return {
            "persistence_status": "persisted",
            "persisted_draft_claim_count": persisted_count,
            "draft_claims_available": True,
            "draft_claims_scope": _draft_claims_scope_patch(payload),
            "targeted_read_kind": "draft_claims_by_work_item_or_source_unit",
        }
    return {
        "persistence_status": "unknown",
        "persisted_draft_claim_count": persisted_count or 0,
        "draft_claims_available": False,
    }


def _targeted_read_hint_patch(
    final_work_item_status: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    persisted_count = _optional_payload_int(payload, "persisted_draft_claim_count")
    available = (
        final_work_item_status == "completed"
        and persisted_count is not None
        and persisted_count > 0
        and not _valid_empty_accepted(payload)
    )
    patch: dict[str, object] = {"available": available}
    if available:
        patch["targeted_read_kind"] = "draft_claims_by_work_item_or_source_unit"
        patch["targeted_read_params"] = _draft_claims_scope_patch(payload)
    return patch


def _draft_claims_scope_patch(payload: Mapping[str, object]) -> Mapping[str, object]:
    return {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "source_unit_ref": _payload_text(payload, "source_unit_ref"),
        "work_item_id": _payload_text(payload, "work_item_id"),
        "dispatch_attempt_id": _payload_text(payload, "dispatch_attempt_id"),
    }


def _work_item_outcome_patch(
    final_work_item_status: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "final_work_item_status": final_work_item_status,
        "attempt_outcome": _dispatch_attempt_outcome(final_work_item_status),
    }
    if final_work_item_status == "retryable":
        patch["retry_eligibility"] = "eligible_for_future_admission"
        patch["retry_driver"] = "capacity_window_admission"
        patch["failure_reason_category"] = _failure_reason_category(payload)
    if final_work_item_status == "terminal_failed":
        reason_category = _failure_reason_category(payload)
        patch["retry_eligibility"] = "not_eligible"
        patch["failure_reason_category"] = reason_category
        patch["terminal_reason"] = reason_category
    return patch


def _dispatch_attempt_outcome(final_work_item_status: str) -> str:
    if final_work_item_status == "completed":
        return "completed"
    if final_work_item_status == "retryable":
        return "retryable_failed"
    return "terminal_failed"


def _capacity_annotation_patch(payload: Mapping[str, object]) -> Mapping[str, object]:
    patch: dict[str, object] = {}
    provider = _optional_payload_text(payload, "provider")
    account_ref = _optional_payload_text(payload, "account_ref")
    model_ref = _optional_payload_text(payload, "model_ref")
    if provider is not None:
        patch["provider"] = provider
    if account_ref is not None:
        patch["account_ref"] = account_ref
    if model_ref is not None:
        patch["model_ref"] = model_ref
    if provider is not None and account_ref is not None and model_ref is not None:
        patch["capacity_window_key"] = f"{provider}:{account_ref}:{model_ref}"
    if _is_capacity_owned_retryable_failure(payload):
        patch["capacity_owned"] = True
    return patch


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
