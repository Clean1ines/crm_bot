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
