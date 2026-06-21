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

_FORBIDDEN_CAPACITY_OVERLAY_FIELDS = frozenset(
    {
        "next_attempt_at",
        "retry_owner",
        "work_item_retry_timer",
    }
)


class CapacityWindowFrontendWorkflowEventProjector:
    """Pure projector for CapacityWindow admission/exhaustion frontend events."""

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
        operation_key = _payload_text(event.payload, "operation_key")
        canonical_phase = _payload_text(event.payload, "canonical_phase")
        payload = _capacity_window_projection_payload(
            projection_type=projection_type,
            source_payload=event.payload,
        )
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


def _projection_type_for_event_type(event_type: str) -> str | None:
    mapping = {
        KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_EXHAUSTED.value: (
            "workflow_capacity_window_exhausted"
        ),
        KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_SCHEDULED_WAKEUP.value: (
            "workflow_capacity_window_scheduled_wakeup"
        ),
        KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_LEASED_WORK_ITEM.value: (
            "workflow_capacity_window_leased_work_item"
        ),
    }
    return mapping.get(event_type)


def _capacity_window_projection_payload(
    *,
    projection_type: str,
    source_payload: Mapping[str, object],
) -> Mapping[str, object]:
    if projection_type == "workflow_capacity_window_exhausted":
        return _exhausted_projection_payload(source_payload)
    if projection_type == "workflow_capacity_window_scheduled_wakeup":
        return _scheduled_wakeup_projection_payload(source_payload)
    if projection_type == "workflow_capacity_window_leased_work_item":
        return _leased_work_item_projection_payload(source_payload)
    raise ValueError(f"unsupported capacity window projection type: {projection_type}")


def _exhausted_projection_payload(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "window_key": _payload_text(payload, "window_key"),
        "provider": _payload_text(payload, "provider"),
        "account_ref": _payload_text(payload, "account_ref"),
        "model_ref": _payload_text(payload, "model_ref"),
        "exhausted_reason": _payload_text(payload, "exhausted_reason"),
        "exhausted_dimensions": _payload_string_list(payload, "exhausted_dimensions"),
        "reset_at": _payload_text(payload, "reset_at"),
        "operation_key": _payload_text(payload, "operation_key"),
        "canonical_phase": _payload_text(payload, "canonical_phase"),
    }
    for optional_key in (
        "observed_at",
        "work_item_id",
        "dispatch_attempt_id",
        "source_unit_ref",
        "causation_command_id",
    ):
        value = payload.get(optional_key)
        if isinstance(value, str) and value.strip():
            patch[optional_key] = value
    _copy_optional_compaction_context(payload, patch)
    return _without_forbidden_fields(patch)


def _scheduled_wakeup_projection_payload(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "window_key": _payload_text(payload, "window_key"),
        "provider": _payload_text(payload, "provider"),
        "account_ref": _payload_text(payload, "account_ref"),
        "model_ref": _payload_text(payload, "model_ref"),
        "run_after": _payload_text(payload, "run_after"),
        "reset_at": _payload_text(payload, "reset_at"),
        "wakeup_command_id": _payload_text(payload, "wakeup_command_id"),
        "prepare_command_type": _payload_text(payload, "prepare_command_type"),
        "wakeup_reason": _payload_text(payload, "wakeup_reason"),
        "operation_key": _payload_text(payload, "operation_key"),
        "canonical_phase": _payload_text(payload, "canonical_phase"),
    }
    causation_command_id = payload.get("causation_command_id")
    if isinstance(causation_command_id, str) and causation_command_id.strip():
        patch["causation_command_id"] = causation_command_id
    _copy_optional_compaction_context(payload, patch)
    return _without_forbidden_fields(patch)


def _leased_work_item_projection_payload(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "window_key": _payload_text(payload, "window_key"),
        "provider": _payload_text(payload, "provider"),
        "account_ref": _payload_text(payload, "account_ref"),
        "model_ref": _payload_text(payload, "model_ref"),
        "work_item_id": _payload_text(payload, "work_item_id"),
        "dispatch_attempt_id": _payload_text(payload, "dispatch_attempt_id"),
        "lease_expires_at": _payload_text(payload, "lease_expires_at"),
        "selection_kind": _payload_text(payload, "selection_kind"),
        "operation_key": _payload_text(payload, "operation_key"),
        "canonical_phase": _payload_text(payload, "canonical_phase"),
        "admission_driver": "capacity_window_admission",
    }
    for optional_key in (
        "source_unit_ref",
        "token_estimate",
        "reserved_tokens",
        "causation_command_id",
    ):
        value = payload.get(optional_key)
        if isinstance(value, str) and value.strip():
            patch[optional_key] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            patch[optional_key] = value
    _copy_optional_compaction_context(payload, patch)
    return _without_forbidden_fields(patch)


def _copy_optional_compaction_context(
    source_payload: Mapping[str, object],
    projected_payload: dict[str, object],
) -> None:
    raw_context = source_payload.get("compaction_context")
    if raw_context is None:
        return
    if not isinstance(raw_context, Mapping):
        raise ValueError("event payload compaction_context must be mapping")
    context: dict[str, object] = {}
    for key in (
        "group_ref",
        "batch_ref",
        "work_item_id",
        "dispatch_attempt_id",
        "expected_output_kind",
    ):
        value = raw_context.get(key)
        if isinstance(value, str) and value.strip():
            context[key] = value
    for key in ("input_node_refs", "input_claim_refs"):
        value = raw_context.get(key)
        if isinstance(value, list):
            refs: list[str] = []
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"event payload compaction_context.{key} must contain text"
                    )
                refs.append(item)
            context[key] = refs
    if context:
        projected_payload["compaction_context"] = context
        projected_payload["targeted_read"] = {
            "kind": "draft_claim_compaction_pending_work_by_workflow_or_group",
            "params": {
                "workflow_run_id": projected_payload["workflow_run_id"],
                "group_ref": context.get("group_ref"),
                "work_item_id": context.get("work_item_id"),
            },
        }


def _without_forbidden_fields(payload: dict[str, object]) -> Mapping[str, object]:
    for forbidden_key in _FORBIDDEN_CAPACITY_OVERLAY_FIELDS:
        if forbidden_key in payload:
            raise ValueError(
                f"capacity window projection must not include {forbidden_key}"
            )
    return payload


def _payload_string_list(payload: Mapping[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"event payload {key} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"event payload {key} must contain non-empty text")
        result.append(item)
    if not result:
        raise ValueError(f"event payload {key} must not be empty")
    return result


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
