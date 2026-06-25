from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.observability.application.projectors.route_activation_frontend_workflow_event_projector import (
    RouteActivationFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:doc-1"


def _event(event_type: str, payload: dict[str, object]) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(f"workflow-event:{_workflow_run_id()}:{event_type}:1"),
        event_type=event_type,
        workflow_run_id=_workflow_run_id(),
        payload=payload,
        occurred_at=_now(),
        sequence_number=7,
    )


def test_projects_route_activation_created() -> None:
    projected = RouteActivationFrontendWorkflowEventProjector().project(
        _event(
            KnowledgeExtractionCanonicalEventType.ROUTE_ACTIVATION_CREATED.value,
            {
                "workflow_run_id": _workflow_run_id(),
                "canonical_phase": "CLAIM_BUILDER_SECTION_EXTRACTION",
                "operation_key": "route_activation",
                "route_activation_ref": "claim_builder:primary:qwen",
                "work_kind": "knowledge_workbench.claim_builder.section_extraction",
                "provider": "groq",
                "model_ref": "qwen/qwen3-32b",
                "route_kind": "primary",
                "route_reason": "normal",
                "activation_scope": "phase",
                "status": "active",
            },
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_route_activation_created"
    assert projected.payload["route_activation_ref"] == "claim_builder:primary:qwen"
    assert projected.payload["route_kind"] == "primary"


def test_projects_work_item_reroute_requested() -> None:
    projected = RouteActivationFrontendWorkflowEventProjector().project(
        _event(
            KnowledgeExtractionCanonicalEventType.WORK_ITEM_REROUTE_REQUESTED.value,
            {
                "workflow_run_id": _workflow_run_id(),
                "canonical_phase": "CLAIM_BUILDER_SECTION_EXTRACTION",
                "operation_key": "execute_claim_builder_section",
                "work_item_id": "work-1",
                "work_kind": "knowledge_workbench.claim_builder.section_extraction",
                "previous_route_activation_ref": "claim_builder:primary:qwen",
                "next_route_activation_ref": "claim_builder:special:input:gpt-oss",
                "route_reason": "input_too_large",
                "source_unit_ref": "source-unit-1",
                "previous_model_ref": "qwen/qwen3-32b",
                "next_model_ref": "openai/gpt-oss-120b",
                "estimated_input_tokens": 9000,
                "reserved_total_tokens": 12000,
            },
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_work_item_reroute_requested"
    assert projected.payload["work_item_id"] == "work-1"
    assert projected.payload["route_reason"] == "input_too_large"
    assert projected.payload["reserved_total_tokens"] == 12000
