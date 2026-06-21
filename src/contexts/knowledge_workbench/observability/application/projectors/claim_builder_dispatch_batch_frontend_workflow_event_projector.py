from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent


PROJECTION_VERSION = 1


class ClaimBuilderDispatchBatchFrontendWorkflowEventProjector:
    """Pure projector for claim-builder dispatch batch prepared frontend events."""

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
        is_attempt_event = (
            event.event_type
            == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value
        )
        project_id, document_id = _document_scope_from_workflow_run_id(workflow_run_id)
        projection_type = (
            "workflow_claim_builder_dispatch_attempt_prepared"
            if is_attempt_event
            else "workflow_dispatch_batch_prepared"
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
            operation_key="prepare_claim_builder_dispatch_batch",
            canonical_phase=(
                KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
            ),
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=(
                _dispatch_attempt_prepared_patch(event.payload)
                if is_attempt_event
                else _dispatch_batch_prepared_patch(event.payload)
            ),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _dispatch_batch_prepared_patch(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "work_kind": _payload_text(payload, "work_kind"),
        "prepared_dispatch_count": _payload_non_negative_int(
            payload,
            "prepared_dispatch_count",
        ),
        "dispatch_attempt_ids": _payload_text_sequence(payload, "dispatch_attempt_ids"),
        "work_item_ids": _payload_text_sequence(payload, "work_item_ids"),
        "input_size_preflight_decision": _payload_text(
            payload,
            "input_size_preflight_decision",
        ),
        "input_size_preflight_reason": _payload_text(
            payload,
            "input_size_preflight_reason",
        ),
    }
    active_model_ref = _optional_payload_text(
        payload,
        "input_size_preflight_active_model_ref",
    )
    if active_model_ref is not None:
        patch["input_size_preflight_active_model_ref"] = active_model_ref

    source_unit_refs = _optional_payload_text_sequence(payload, "source_unit_refs")
    if source_unit_refs is not None:
        patch["source_unit_refs"] = source_unit_refs

    affected_work_item_refs = _optional_payload_text_sequence(
        payload,
        "affected_work_item_refs",
    )
    if affected_work_item_refs is not None:
        patch["affected_work_item_refs"] = affected_work_item_refs

    return patch


def _dispatch_attempt_prepared_patch(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    patch: dict[str, object] = {
        "workflow_run_id": _payload_text(payload, "workflow_run_id"),
        "source_document_ref": _payload_text(payload, "source_document_ref"),
        "source_unit_ref": _payload_text(payload, "source_unit_ref"),
        "work_item_id": _payload_text(payload, "work_item_id"),
        "work_kind": _payload_text(payload, "work_kind"),
        "dispatch_attempt_id": _payload_text(payload, "dispatch_attempt_id"),
        "attempt_number": _payload_non_negative_int(payload, "attempt_number"),
        "attempt_state": _payload_text(payload, "attempt_state"),
        "provider": _payload_text(payload, "provider"),
        "account_ref": _payload_text(payload, "account_ref"),
        "model_ref": _payload_text(payload, "model_ref"),
    }
    lease_expires_at = _optional_payload_text(payload, "lease_expires_at")
    if lease_expires_at is not None:
        patch["lease_expires_at"] = lease_expires_at
    return patch


_SUPPORTED_EVENT_TYPES = frozenset(
    {
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED.value,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value,
    }
)


def _document_scope_from_workflow_run_id(workflow_run_id: str) -> tuple[str, str]:
    prefix = "knowledge-extraction:source-document:"
    if not workflow_run_id.startswith(prefix):
        raise ValueError("workflow_run_id must include source document scope")
    remainder = workflow_run_id.removeprefix(prefix)
    parts = remainder.split(":", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise ValueError("workflow_run_id must include project_id and document suffix")
    project_id = parts[0]
    document_id = f"source-document:{remainder}"
    return project_id, document_id


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


def _payload_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"event payload {key} must be int")
    if value < 0:
        raise ValueError(f"event payload {key} must be >= 0")
    return value


def _payload_text_sequence(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"event payload {key} must be a sequence")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"event payload {key} must contain non-empty text")
        items.append(item)
    return tuple(items)


def _optional_payload_text_sequence(
    payload: Mapping[str, object],
    key: str,
) -> tuple[str, ...] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"event payload {key} must be a sequence")
    if len(value) == 0:
        return None
    return _payload_text_sequence(payload, key)
