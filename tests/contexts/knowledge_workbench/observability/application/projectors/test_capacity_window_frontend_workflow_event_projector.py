from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.projectors.capacity_window_frontend_workflow_event_projector import (
    CapacityWindowFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _event(
    *,
    event_type: str,
    payload: dict[str, object],
    event_suffix: str = "evt-1",
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{_workflow_run_id()}:{event_type}:{event_suffix}"
        ),
        event_type=event_type,
        workflow_run_id=_workflow_run_id(),
        payload=payload,
        occurred_at=_now(),
        sequence_number=42,
    )


def test_projects_capacity_window_exhausted_without_retry_overlay_fields() -> None:
    projected = CapacityWindowFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_EXHAUSTED.value
            ),
            payload={
                "workflow_run_id": _workflow_run_id(),
                "window_key": "groq:groq_org_primary:qwen/qwen3-32b",
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "exhausted_reason": "provider_capacity_limit",
                "exhausted_dimensions": ["minute_requests"],
                "reset_at": "2026-06-21T12:01:00+00:00",
                "operation_key": "execute_claim_builder_section",
                "canonical_phase": (
                    KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
                ),
            },
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_capacity_window_exhausted"
    assert projected.payload["reset_at"] == "2026-06-21T12:01:00+00:00"
    for forbidden in ("next_attempt_at", "retry_owner", "work_item_retry_timer"):
        assert forbidden not in projected.payload


def test_projects_capacity_window_scheduled_wakeup_as_command_delivery() -> None:
    projected = CapacityWindowFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_SCHEDULED_WAKEUP.value
            ),
            payload={
                "workflow_run_id": _workflow_run_id(),
                "window_key": "groq:groq_org_primary:qwen/qwen3-32b",
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "run_after": "2026-06-21T12:01:00+00:00",
                "reset_at": "2026-06-21T12:01:00+00:00",
                "wakeup_command_id": "workflow-command:wakeup-1",
                "prepare_command_type": "PrepareClaimBuilderDispatchBatch",
                "wakeup_reason": "provider_minute_reset",
                "operation_key": "execute_claim_builder_section",
                "canonical_phase": (
                    KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
                ),
            },
            event_suffix="wakeup-1",
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_capacity_window_scheduled_wakeup"
    assert projected.payload["run_after"] == "2026-06-21T12:01:00+00:00"
    assert "work_item_retry_timer" not in projected.payload


def test_projects_capacity_window_leased_work_item_with_selection_kind() -> None:
    projected = CapacityWindowFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_LEASED_WORK_ITEM.value
            ),
            payload={
                "workflow_run_id": _workflow_run_id(),
                "window_key": "groq:groq_org_primary:qwen/qwen3-32b",
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "work_item_id": "work-1",
                "dispatch_attempt_id": "work-1:attempt:1",
                "lease_expires_at": "2026-06-21T12:02:00+00:00",
                "selection_kind": "retryable",
                "operation_key": "prepare_claim_builder_dispatch_batch",
                "canonical_phase": (
                    KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
                ),
            },
            event_suffix="work-1:attempt:1",
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_capacity_window_leased_work_item"
    assert projected.payload["selection_kind"] == "retryable"
    assert projected.payload["admission_driver"] == "capacity_window_admission"
    assert "next_attempt_at" not in projected.payload


def test_ignores_forbidden_overlay_fields_when_present_in_canonical_payload() -> None:
    projected = CapacityWindowFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_EXHAUSTED.value
            ),
            payload={
                "workflow_run_id": _workflow_run_id(),
                "window_key": "groq:groq_org_primary:qwen/qwen3-32b",
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "exhausted_reason": "provider_capacity_limit",
                "exhausted_dimensions": ["minute_requests"],
                "reset_at": "2026-06-21T12:01:00+00:00",
                "operation_key": "execute_claim_builder_section",
                "canonical_phase": (
                    KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
                ),
                "next_attempt_at": "2026-06-21T12:05:00+00:00",
                "retry_owner": "work_item",
            },
        )
    )

    assert projected is not None
    assert "next_attempt_at" not in projected.payload
    assert "retry_owner" not in projected.payload


def test_projects_capacity_window_waiting_due_work_with_route_context() -> None:
    projected = CapacityWindowFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_WAITING_DUE_WORK.value
            ),
            payload={
                "workflow_run_id": _workflow_run_id(),
                "window_key": "groq:groq_org_primary:qwen/qwen3-32b",
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "waiting_reason": "active_leased_wait",
                "active_leased_count": 1,
                "operation_key": "prepare_claim_builder_dispatch_batch",
                "canonical_phase": (
                    KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
                ),
                "route_activation_ref": "claim_builder:primary:qwen",
                "route_kind": "primary",
                "route_reason": "normal",
                "capacity_scope_ref": "groq:groq_org_primary:qwen/qwen3-32b",
                "slot_ref": "groq:groq_org_primary:qwen/qwen3-32b:slot-1",
            },
            event_suffix="waiting-due-work",
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_capacity_window_waiting_due_work"
    assert projected.payload["waiting_reason"] == "active_leased_wait"
    assert projected.payload["active_leased_count"] == 1
    assert projected.payload["route_context"] == {
        "route_activation_ref": "claim_builder:primary:qwen",
        "route_kind": "primary",
        "route_reason": "normal",
        "capacity_scope_ref": "groq:groq_org_primary:qwen/qwen3-32b",
        "slot_ref": "groq:groq_org_primary:qwen/qwen3-32b:slot-1",
    }
    assert "next_attempt_at" not in projected.payload


def test_projects_capacity_window_admission_skipped() -> None:
    projected = CapacityWindowFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_ADMISSION_SKIPPED.value
            ),
            payload={
                "workflow_run_id": _workflow_run_id(),
                "window_key": "groq:groq_org_primary:qwen/qwen3-32b",
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "skipped_reason": "execution_lease_lost",
                "work_item_id": "work-1",
                "operation_key": "prepare_claim_builder_dispatch_batch",
                "canonical_phase": (
                    KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
                ),
            },
            event_suffix="admission-skipped",
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_capacity_window_admission_skipped"
    assert projected.payload["skipped_reason"] == "execution_lease_lost"
    assert projected.payload["work_item_id"] == "work-1"
    assert projected.payload["admission_driver"] == "capacity_window_admission"
    assert "work_item_retry_timer" not in projected.payload


def test_compaction_capacity_event_projects_attachable_work_context() -> None:
    projected = CapacityWindowFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_LEASED_WORK_ITEM.value
            ),
            payload={
                "workflow_run_id": "workflow-1",
                "window_key": "groq:account-1:model-1",
                "provider": "groq",
                "account_ref": "account-1",
                "model_ref": "model-1",
                "work_item_id": "claim-compaction:workflow-1:batch-1",
                "dispatch_attempt_id": "attempt-1",
                "lease_expires_at": "2026-01-01T00:01:00+00:00",
                "selection_kind": "fresh",
                "operation_key": "prepare_draft_claim_compaction_dispatch_batch",
                "canonical_phase": "DRAFT_CLAIM_CLUSTERING",
                "compaction_context": {
                    "group_ref": "group-1",
                    "batch_ref": "batch-1",
                    "work_item_id": "claim-compaction:workflow-1:batch-1",
                    "dispatch_attempt_id": "attempt-1",
                    "input_node_refs": ["node-1", "node-2"],
                    "input_claim_refs": ["claim-1", "claim-2"],
                },
            },
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_capacity_window_leased_work_item"
    assert projected.payload["compaction_context"] == {
        "group_ref": "group-1",
        "batch_ref": "batch-1",
        "work_item_id": "claim-compaction:workflow-1:batch-1",
        "dispatch_attempt_id": "attempt-1",
        "input_node_refs": ["node-1", "node-2"],
        "input_claim_refs": ["claim-1", "claim-2"],
    }
    assert projected.payload["targeted_read"]["kind"] == (
        "draft_claim_compaction_pending_work_by_workflow_or_group"
    )
    assert "next_attempt_at" not in str(projected.payload)
    assert "retry_owner" not in str(projected.payload)
    assert "work_item_retry_timer" not in str(projected.payload)
