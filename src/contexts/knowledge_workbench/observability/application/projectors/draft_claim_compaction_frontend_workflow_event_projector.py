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
_EXPECTED_PHASE = KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
_COMPACTION_WORK_KIND = "knowledge_workbench.draft_claim_compaction"


_PROJECTION_TYPES = {
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED.value: (
        "workflow_draft_claim_compaction_dispatch_batch_prepared"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED.value: (
        "workflow_draft_claim_compaction_attempt_completed"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_RETRYABLE_FAILED.value: (
        "workflow_draft_claim_compaction_attempt_retryable_failed"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_TERMINAL_FAILED.value: (
        "workflow_draft_claim_compaction_attempt_terminal_failed"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value: (
        "workflow_draft_claim_compaction_result_applied"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_NEXT_WORK_SCHEDULED.value: (
        "workflow_draft_claim_compaction_next_work_scheduled"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_CLUSTER_DONE.value: (
        "workflow_draft_claim_compaction_cluster_done"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ALL_GROUPS_COMPACTED.value: (
        "workflow_draft_claim_compaction_all_groups_compacted"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value: (
        "workflow_draft_claim_compaction_progress_reconciled"
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value: (
        "workflow_draft_claim_compaction_waiting_user_model_choice"
    ),
}


_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "workflow_run_id",
        "work_kind",
        "work_item_id",
        "work_item_ids",
        "dispatch_attempt_id",
        "dispatch_attempt_ids",
        "dispatch_contexts",
        "group_ref",
        "batch_ref",
        "source_claim_refs",
        "source_node_refs",
        "raw_claim_refs",
        "compacted_node_refs",
        "input_node_refs",
        "input_claim_refs",
        "outcome_status",
        "provider",
        "account_ref",
        "model_ref",
        "actual_prompt_tokens",
        "actual_completion_tokens",
        "actual_total_tokens",
        "error_kind",
        "draft_claim_compaction_validation_decision",
        "validated_compacted_claim_count",
        "validation_error",
        "retry_recommended",
        "created_node_refs",
        "superseded_node_refs",
        "comparison_refs",
        "next_work_type",
        "reason",
        "scheduled_work_item_count",
        "already_scheduled_work_item_count",
        "appended_next_command_count",
        "next_command_type",
        "next_batch",
        "summary",
        "primary_model_id",
        "degraded_candidate_model_id",
        "node_refs",
        "resume_work_type",
        "prompt_tokens",
        "artifact_tokens",
    }
)


class DraftClaimCompactionFrontendWorkflowEventProjector:
    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")

        projection_type = _PROJECTION_TYPES.get(event.event_type)
        if projection_type is None:
            return None
        if event.sequence_number is None:
            raise ValueError("event sequence_number is required for frontend projection")

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
            operation_key=_operation_key(event.event_type),
            canonical_phase=_EXPECTED_PHASE,
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=_projection_payload(event.payload),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _projection_payload(payload: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in _ALLOWED_PAYLOAD_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if value is not None:
            result[key] = _json_value(value)
    result.setdefault("work_kind", _COMPACTION_WORK_KIND)
    return result


def _operation_key(event_type: str) -> str:
    if event_type == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED.value:
        return "prepare_draft_claim_compaction_dispatch_batch"
    if event_type in {
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_RETRYABLE_FAILED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_TERMINAL_FAILED.value,
    }:
        return "execute_draft_claim_compaction"
    if event_type == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value:
        return "apply_draft_claim_compaction_result"
    if event_type == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value:
        return "reconcile_draft_claim_compaction_progress"
    return "draft_claim_compaction"


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


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return str(value)
