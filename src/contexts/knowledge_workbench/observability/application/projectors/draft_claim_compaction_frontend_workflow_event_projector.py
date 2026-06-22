from __future__ import annotations

from collections.abc import Mapping
from typing import cast

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

_HEAVY_OUTPUT_KEYS = frozenset(
    {
        "compacted_claim",
        "compacted_claims",
        "reduced_rewrite",
        "claim",
        "possible_questions",
        "exclusion_scope",
        "evidence_block",
        "source_claim_refs",
        "target_claim_refs",
        "triples",
        "raw_output",
        "parsed_output",
        "model_output",
        "messages",
        "group_members",
        "member_claims",
        "compacted_payload",
    }
)

_FORBIDDEN_TIMER_KEYS = frozenset(
    {
        "retry_owner",
        "work_item_retry_timer",
        "capacity_retry_at",
        "provider_reset_at",
        "provider_wait_until",
        "quota_reset_at",
        "minute_reset_at",
        "daily_reset_at",
        "next_attempt_at",
        "run_after",
        "next_run_after",
        "next_due_at",
    }
)

_ATTEMPT_PROJECTIONS = {
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED.value: (
        "workflow_draft_claim_compaction_attempt_completed",
        "completed",
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_RETRYABLE_FAILED.value: (
        "workflow_draft_claim_compaction_attempt_retryable_failed",
        "retryable_failed",
    ),
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_TERMINAL_FAILED.value: (
        "workflow_draft_claim_compaction_attempt_terminal_failed",
        "terminal_failed",
    ),
}

_OTHER_PROJECTIONS = {
    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED.value: (
        "workflow_draft_claim_compaction_dispatch_batch_prepared"
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


class DraftClaimCompactionFrontendWorkflowEventProjector:
    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")
        projection_type = _projection_type(event.event_type)
        if projection_type is None:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )

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
            payload=_projection_payload(event),
            occurred_at=event.occurred_at,
            causation_command_id=(
                event.causation_command_id.value
                if event.causation_command_id is not None
                else None
            ),
            correlation_id=event.correlation_id,
            projected_at=event.occurred_at,
        )


def _projection_type(event_type: str) -> str | None:
    if event_type in _ATTEMPT_PROJECTIONS:
        return _ATTEMPT_PROJECTIONS[event_type][0]
    return _OTHER_PROJECTIONS.get(event_type)


def _operation_key(event_type: str) -> str:
    if event_type in _ATTEMPT_PROJECTIONS:
        return "execute_draft_claim_compaction"
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED.value
    ):
        return "prepare_draft_claim_compaction_dispatch_batch"
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value
    ):
        return "apply_draft_claim_compaction_result"
    if (
        event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value
    ):
        return "reconcile_draft_claim_compaction_progress"
    return "draft_claim_compaction"


def _projection_payload(event: WorkflowEvent) -> dict[str, object]:
    if event.event_type in _ATTEMPT_PROJECTIONS:
        return _attempt_payload(
            event.payload,
            work_item_state=_ATTEMPT_PROJECTIONS[event.event_type][1],
        )
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value
    ):
        return _result_applied_payload(event.payload)
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_NEXT_WORK_SCHEDULED.value
    ):
        return _next_work_payload(event.payload)
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_CLUSTER_DONE.value
    ):
        return _cluster_done_payload(event.payload)
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ALL_GROUPS_COMPACTED.value
    ):
        return _all_groups_compacted_payload(event.payload)
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value
    ):
        return _progress_reconciled_payload(event.payload)
    if (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value
    ):
        return _waiting_user_choice_payload(event.payload)
    return _dispatch_prepared_payload(event.payload)


def _attempt_payload(
    payload: Mapping[str, object], *, work_item_state: str
) -> dict[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    work_item_id = _payload_text(payload, "work_item_id")
    dispatch_attempt_id = _payload_text(payload, "dispatch_attempt_id")
    group_ref = _optional_payload_text(payload, "group_ref")
    batch_ref = _optional_payload_text(payload, "batch_ref")
    input_node_refs = _input_node_refs_from_payload(payload)
    input_claim_refs = _payload_text_list(payload, "source_claim_refs")
    outcome_status = (
        _optional_payload_text(payload, "outcome_status") or work_item_state
    )
    expected_output_kind = _safe_compaction_result_kind(
        _optional_payload_text(payload, "expected_output_kind")
    )

    patch: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "work_item_id": work_item_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_kind": _optional_payload_text(payload, "work_kind")
        or _COMPACTION_WORK_KIND,
        "entity_contract": _compaction_entity_contract(),
        "pending_reduction_work": {
            "surface_kind": "draft_claim_compaction_pending_reduction_work",
            "row_key": work_item_id,
            "key_field": "work_item_id",
            "attempt_history_key_field": "dispatch_attempt_id",
            "append_attempt": True,
            "workflow_run_id": workflow_run_id,
            "group_ref": group_ref,
            "batch_ref": batch_ref,
            "input_node_refs": input_node_refs,
            "input_claim_refs": input_claim_refs,
            "targeted_read": _pending_work_targeted_read(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                work_item_id=work_item_id,
            ),
        },
        "compaction_attempt": {
            "surface_kind": "draft_claim_compaction_attempt",
            "history_key": dispatch_attempt_id,
            "key_field": "dispatch_attempt_id",
            "parent_work_item_id": work_item_id,
            "append_only": True,
            "workflow_run_id": workflow_run_id,
        },
        "attempt_outcome": {
            "attempt_scope": _drop_none(
                {
                    "workflow_run_id": workflow_run_id,
                    "work_item_id": work_item_id,
                    "dispatch_attempt_id": dispatch_attempt_id,
                    "group_ref": group_ref,
                    "batch_ref": batch_ref,
                    "input_node_refs": input_node_refs or None,
                    "input_claim_refs": input_claim_refs or None,
                }
            ),
            "provider_outcome": _drop_none(
                {
                    "provider": _safe_json_value(payload, "provider"),
                    "account_ref": _safe_json_value(payload, "account_ref"),
                    "model_ref": _safe_json_value(payload, "model_ref"),
                    "status": outcome_status,
                    "prompt_tokens": _safe_json_value(payload, "actual_prompt_tokens"),
                    "completion_tokens": _safe_json_value(
                        payload, "actual_completion_tokens"
                    ),
                    "total_tokens": _safe_json_value(payload, "actual_total_tokens"),
                    "error_kind": _safe_json_value(payload, "error_kind"),
                }
            ),
            "validation_outcome": _drop_none(
                {
                    "validation_status": _validation_status(payload),
                    "validation_decision": _safe_json_value(
                        payload,
                        "draft_claim_compaction_validation_decision",
                    ),
                    "expected_output_kind": expected_output_kind,
                    "validated_compacted_claim_count": _safe_json_value(
                        payload,
                        "validated_compacted_claim_count",
                    ),
                    "validation_error": _safe_json_value(payload, "validation_error"),
                    "retry_recommended": _safe_json_value(payload, "retry_recommended"),
                }
            ),
            "work_item_outcome": {
                "work_item_state": work_item_state,
                "completed": work_item_state == "completed",
                "retryable": work_item_state == "retryable_failed",
                "terminal": work_item_state == "terminal_failed",
            },
            "capacity_annotation": {
                "capacity_window_owned": True,
                "no_work_item_retry_timer": True,
            },
            "result_pointer": _drop_none(
                {
                    "result_kind": expected_output_kind,
                    "result_applied": False,
                    "generated_nodes_available": False,
                }
            ),
        },
    }
    _assert_no_forbidden_payload(patch)
    return patch


def _result_applied_payload(payload: Mapping[str, object]) -> dict[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    group_ref = _payload_text(payload, "group_ref")
    batch_ref = _payload_text(payload, "batch_ref")
    work_item_id = _payload_text(payload, "work_item_id")
    created_node_refs = _payload_text_list(payload, "created_node_refs")
    superseded_node_refs = _payload_text_list(payload, "superseded_node_refs")
    comparison_refs = _payload_text_list(payload, "comparison_refs")

    patch: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "group_ref": group_ref,
        "batch_ref": batch_ref,
        "work_item_id": work_item_id,
        "created_node_count": len(created_node_refs),
        "created_node_refs": created_node_refs,
        "superseded_node_count": len(superseded_node_refs),
        "superseded_node_refs": superseded_node_refs,
        "comparison_count": len(comparison_refs),
        "comparison_refs": comparison_refs,
        "next_work_type": _optional_payload_text(payload, "next_work_type"),
        "generated_compaction_nodes": _generated_nodes_patch(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            batch_ref=batch_ref,
            work_item_id=work_item_id,
            created_node_refs=created_node_refs,
        ),
        "frontier_update": {
            "availability": "changed",
            "reason": "result_applied",
            "generated_nodes_available": True,
            "targeted_read": _frontier_targeted_read(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
            ),
        },
        "targeted_reads": [
            _nodes_targeted_read(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                active_only=False,
            ),
            _frontier_targeted_read(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
            ),
        ],
    }
    _assert_no_forbidden_payload(patch)
    return patch


def _generated_nodes_patch(
    *,
    workflow_run_id: str,
    group_ref: str,
    batch_ref: str,
    work_item_id: str,
    created_node_refs: list[str],
) -> dict[str, object]:
    result: dict[str, object] = {
        "surface_kind": "draft_claim_compaction_node",
        "availability": "available",
        "parent_scope": {
            "workflow_run_id": workflow_run_id,
            "group_ref": group_ref,
            "batch_ref": batch_ref,
            "work_item_id": work_item_id,
        },
        "targeted_read": _nodes_targeted_read(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            active_only=False,
        ),
    }
    if created_node_refs:
        result["created_node_refs"] = created_node_refs
        result["created_node_count"] = len(created_node_refs)
    else:
        result["created_node_ref_gap"] = "result_applied_event_has_no_created_node_refs"
    return result


def _next_work_payload(payload: Mapping[str, object]) -> dict[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    group_ref = _payload_text(payload, "group_ref")
    return {
        "workflow_run_id": workflow_run_id,
        "group_ref": group_ref,
        "reason": _optional_payload_text(payload, "reason"),
        "next_work_type": _optional_payload_text(payload, "next_work_type"),
        "scheduled_work_item_count": _payload_int_default(
            payload, "scheduled_work_item_count", default=0
        ),
        "already_scheduled_work_item_count": _payload_int_default(
            payload, "already_scheduled_work_item_count", default=0
        ),
        "appended_next_command_count": _payload_int_default(
            payload, "appended_next_command_count", default=0
        ),
        "next_compaction_work": {
            "availability": "scheduled",
            "parent_scope": {
                "workflow_run_id": workflow_run_id,
                "group_ref": group_ref,
            },
            "does_not_create_cluster_batch_rows": True,
            "targeted_read": _pending_work_targeted_read(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
            ),
            "targeted_reads": [
                _pending_work_targeted_read(
                    workflow_run_id=workflow_run_id,
                    group_ref=group_ref,
                ),
                _frontier_targeted_read(
                    workflow_run_id=workflow_run_id,
                    group_ref=group_ref,
                ),
            ],
        },
    }


def _cluster_done_payload(payload: Mapping[str, object]) -> dict[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    group_ref = _payload_text(payload, "group_ref")
    return {
        "workflow_run_id": workflow_run_id,
        "group_ref": group_ref,
        "cluster_group_compaction": {
            "status": "completed",
            "scope": {"workflow_run_id": workflow_run_id, "group_ref": group_ref},
            "document_compaction_completed": False,
        },
    }


def _all_groups_compacted_payload(payload: Mapping[str, object]) -> dict[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    return {
        "workflow_run_id": workflow_run_id,
        "summary": _safe_summary_payload(payload),
        "next_command_type": _safe_json_value(payload, "next_command_type"),
        "document_compaction": {
            "status": "completed",
            "workflow_run_id": workflow_run_id,
            "curation_readiness": "ready_to_open_workspace",
            "publication_ready": False,
        },
    }


def _progress_reconciled_payload(payload: Mapping[str, object]) -> dict[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    return {
        "workflow_run_id": workflow_run_id,
        "decision": _optional_payload_text(payload, "decision"),
        "summary": _safe_summary_payload(payload),
        "next_command_type": _safe_json_value(payload, "next_command_type"),
    }


def _waiting_user_choice_payload(payload: Mapping[str, object]) -> dict[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    return {
        "workflow_run_id": workflow_run_id,
        "summary": _safe_summary_payload(payload),
        "model_choice": {
            "required": True,
            "scope": {"workflow_run_id": workflow_run_id},
        },
    }


def _dispatch_prepared_payload(payload: Mapping[str, object]) -> dict[str, object]:
    workflow_run_id = _payload_text(payload, "workflow_run_id")
    dispatch_attempt_ids = _payload_text_list(payload, "dispatch_attempt_ids")
    work_item_ids = _payload_text_list(payload, "work_item_ids")
    dispatch_contexts = _payload_mapping_list(payload, "dispatch_contexts")
    return {
        "workflow_run_id": workflow_run_id,
        "work_kind": _optional_payload_text(payload, "work_kind")
        or _COMPACTION_WORK_KIND,
        "prepared_dispatch_attempt_count": len(dispatch_attempt_ids),
        "dispatch_attempt_ids": dispatch_attempt_ids,
        "work_item_ids": work_item_ids,
        "compaction_work_item_overlay": {
            "availability": "prepared",
            "workflow_run_id": workflow_run_id,
            "capacity_window_owned": True,
        },
        "entity_contract": _compaction_entity_contract(),
        "pending_reduction_work_rows": {
            "surface_kind": "draft_claim_compaction_pending_reduction_work",
            "row_key_field": "work_item_id",
            "attempt_history_key_field": "dispatch_attempt_id",
            "availability": "prepared",
            "rows": dispatch_contexts,
            "targeted_read": _pending_work_targeted_read(
                workflow_run_id=workflow_run_id,
            ),
        },
        "compaction_attempt_rows": {
            "surface_kind": "draft_claim_compaction_attempt",
            "row_key_field": "dispatch_attempt_id",
            "parent_key_field": "work_item_id",
            "append_only": True,
            "dispatch_attempt_ids": dispatch_attempt_ids,
        },
        "targeted_reads": [
            _pending_work_targeted_read(workflow_run_id=workflow_run_id),
            _frontier_targeted_read(workflow_run_id=workflow_run_id),
        ],
    }


def _validation_status(payload: Mapping[str, object]) -> str | None:
    decision = _safe_json_value(payload, "draft_claim_compaction_validation_decision")
    if decision == "valid_output":
        return "valid"
    if decision == "invalid_output":
        return "invalid"
    return None


def _safe_compaction_result_kind(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if value == "compacted_claims":
        return "compacted_node"
    if value == "reduced_rewrite":
        return "reduced_rewrite_node"
    return value


def _compaction_entity_contract() -> dict[str, object]:
    return {
        "cluster_group_key": "group_ref",
        "initial_cluster_batch_key": "batch_ref",
        "dynamic_reduction_work_key": "work_item_id",
        "attempt_history_key": "dispatch_attempt_id",
        "capacity_window_key": "window_key",
        "frontier_artifact_key": "node_ref",
        "attempts_append_under": "pending_reduction_work[work_item_id]",
        "cluster_batch_is_initial_surface_only": True,
        "dynamic_work_is_not_fake_cluster_batch": True,
    }


def _nodes_targeted_read(
    *,
    workflow_run_id: str,
    group_ref: str | None,
    active_only: bool,
) -> dict[str, object]:
    return {
        "kind": "draft_claim_compaction_nodes_by_workflow_or_group",
        "params": _drop_none(
            {
                "workflow_run_id": workflow_run_id,
                "group_ref": group_ref,
                "active_only": active_only,
            }
        ),
    }


def _frontier_targeted_read(
    *,
    workflow_run_id: str,
    group_ref: str | None = None,
) -> dict[str, object]:
    return {
        "kind": "draft_claim_compaction_frontier_by_workflow_or_group",
        "params": _drop_none(
            {
                "workflow_run_id": workflow_run_id,
                "group_ref": group_ref,
                "include_inactive": True,
            }
        ),
    }


def _pending_work_targeted_read(
    *,
    workflow_run_id: str,
    group_ref: str | None = None,
    work_item_id: str | None = None,
) -> dict[str, object]:
    return {
        "kind": "draft_claim_compaction_pending_work_by_workflow_or_group",
        "params": _drop_none(
            {
                "workflow_run_id": workflow_run_id,
                "group_ref": group_ref,
                "work_item_id": work_item_id,
            }
        ),
    }


def _input_node_refs_from_payload(payload: Mapping[str, object]) -> list[str]:
    for key in ("source_node_refs", "compared_node_refs", "node_refs"):
        refs = _payload_text_list(payload, key)
        if refs:
            return refs
    left_node_ref = _optional_payload_text(payload, "left_node_ref")
    right_node_ref = _optional_payload_text(payload, "right_node_ref")
    if left_node_ref is None:
        return []
    result = [left_node_ref]
    if right_node_ref is not None:
        result.append(right_node_ref)
    return result


def _payload_mapping_list(
    payload: Mapping[str, object],
    key: str,
) -> list[dict[str, object]]:
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list | tuple):
        raise ValueError(f"event payload {key} must be list")
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"event payload {key} must contain mappings")
        row: dict[str, object] = {}
        for row_key, row_value in item.items():
            if not isinstance(row_key, str):
                continue
            if row_key in _HEAVY_OUTPUT_KEYS or row_key in _FORBIDDEN_TIMER_KEYS:
                continue
            if _is_json_value(row_value):
                row[row_key] = row_value
        result.append(row)
    return result


def _safe_summary_payload(payload: Mapping[str, object]) -> dict[str, object]:
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        return {}
    result: dict[str, object] = {}
    for key, value in summary.items():
        if isinstance(key, str) and _is_json_value(value):
            result[key] = value
    _assert_no_forbidden_payload(result)
    return result


def _drop_none(payload: Mapping[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if value is not None}


def _safe_json_value(payload: Mapping[str, object], key: str) -> JsonValue:
    if key in _HEAVY_OUTPUT_KEYS or key in _FORBIDDEN_TIMER_KEYS:
        return None
    value = payload.get(key)
    if _is_json_value(value):
        return cast(JsonValue, value)
    return None


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"event payload {key} must be non-empty text")
    return value


def _optional_payload_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None or not isinstance(value, str) or not value.strip():
        return None
    return value


def _payload_int_default(
    payload: Mapping[str, object], key: str, *, default: int
) -> int:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"event payload {key} must be int")
    if value < 0:
        raise ValueError(f"event payload {key} must be >= 0")
    return value


def _payload_text_list(payload: Mapping[str, object], key: str) -> list[str]:
    value = payload.get(key, [])
    if value is None or not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _document_scope_from_workflow_run_id(workflow_run_id: str) -> tuple[str, str]:
    prefix = "knowledge-extraction:source-document:"
    if workflow_run_id.startswith(prefix):
        remainder = workflow_run_id.removeprefix(prefix)
        parts = remainder.split(":", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0], f"source-document:{remainder}"
    return workflow_run_id, workflow_run_id


def _assert_no_forbidden_payload(payload: object) -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in _HEAVY_OUTPUT_KEYS:
                raise ValueError(
                    f"projection payload must not include heavy body: {key}"
                )
            if key in _FORBIDDEN_TIMER_KEYS:
                raise ValueError(
                    f"projection payload must not include retry timer: {key}"
                )
            _assert_no_forbidden_payload(value)
    elif isinstance(payload, list | tuple):
        for item in payload:
            _assert_no_forbidden_payload(item)


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_json_value(item) for key, item in value.items()
        )
    return False
