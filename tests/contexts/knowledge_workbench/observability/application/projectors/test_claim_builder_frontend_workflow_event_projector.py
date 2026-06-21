from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_frontend_workflow_event_projector import (
    ClaimBuilderFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def test_routes_dispatch_batch_prepared_to_dispatch_projector() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:dispatch-prepared"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "work_kind": "claim_builder_section",
            "prepared_dispatch_count": 1,
            "dispatch_attempt_ids": ("work-1:attempt:1",),
            "work_item_ids": ("work-1",),
            "input_size_preflight_decision": "USE_ACTIVE_MODEL",
            "input_size_preflight_reason": "ok",
            "input_size_preflight_active_model_ref": "qwen/qwen3-32b",
            "source_split_required": False,
            "affected_work_item_refs": (),
            "source_unit_refs": (),
        },
        occurred_at=_now(),
        sequence_number=3,
    )

    projected = ClaimBuilderFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_dispatch_batch_prepared"


def test_routes_capacity_observed_to_capacity_projector() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:capacity-observed"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "source_document_ref": "source-document:project-1:abc",
            "source_unit_ref": "unit-1",
            "dispatch_attempt_id": "work-1:attempt:1",
            "work_item_id": "work-1",
            "operation_key": "execute_claim_builder_section",
            "canonical_phase": "CLAIM_BUILDER_SECTION_EXTRACTION",
            "provider": "groq",
            "account_ref": "groq_org_primary",
            "model_ref": "qwen/qwen3-32b",
            "outcome_class": "succeeded",
            "observed_at": _now().isoformat(),
        },
        occurred_at=_now(),
        sequence_number=4,
    )

    projected = ClaimBuilderFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_capacity_window_observed"


def test_routes_section_extracted_to_outcome_projector() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:section-extracted"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "source_document_ref": "source-document:project-1:abc",
            "source_unit_ref": "unit-1",
            "dispatch_attempt_id": "work-1:attempt:1",
            "work_item_id": "work-1",
            "operation_key": "execute_claim_builder_section",
            "canonical_phase": "CLAIM_BUILDER_SECTION_EXTRACTION",
            "persisted_draft_claim_count": 1,
        },
        occurred_at=_now(),
        sequence_number=5,
    )

    projected = ClaimBuilderFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_claim_builder_section_extracted"


def test_routes_deferred_event_type_to_none() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:section-deferred"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "dispatch_attempt_id": "work-1:attempt:1",
            "work_item_id": "work-1",
            "operation_key": "execute_claim_builder_section",
            "canonical_phase": "CLAIM_BUILDER_SECTION_EXTRACTION",
        },
        occurred_at=_now(),
        sequence_number=6,
    )

    projected = ClaimBuilderFrontendWorkflowEventProjector().project(event)

    assert projected is None


def test_routes_progress_reconciled_to_progress_projector() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:progress-reconciled"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_PROGRESS_RECONCILED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "reconcile_claim_builder_progress",
            "canonical_phase": "CLAIM_BUILDER_SECTION_EXTRACTION",
            "work_kind": "claim_builder_section",
            "decision": "PREPARE_NEXT_BATCH_NOW",
            "summary": {"ready_count": 1, "total_count": 1},
            "retry_action_summary": {"defer_until_capacity_reset_count": 0},
            "selected_retry_plan": None,
            "next_command_type": None,
            "next_run_after": None,
        },
        occurred_at=_now(),
        sequence_number=7,
    )

    projected = ClaimBuilderFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_claim_builder_progress_reconciled"


def test_routes_all_sections_extracted_to_all_sections_projector() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:all-sections-extracted"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "reconcile_claim_builder_progress",
            "canonical_phase": "CLAIM_BUILDER_SECTION_EXTRACTION",
            "work_kind": "claim_builder_section",
            "summary": {"completed_count": 3, "total_count": 3},
            "completed_count": 3,
            "total_count": 3,
            "next_command_type": "GenerateDraftClaimEmbeddings",
        },
        occurred_at=_now(),
        sequence_number=8,
    )

    projected = ClaimBuilderFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_claim_builder_all_sections_extracted"
