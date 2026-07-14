from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.observability.application.projectors.workbench_rag_eval_frontend_workflow_event_projector import (
    WorkbenchRagEvalFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowEventType,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def test_rag_eval_projector_projects_allowlisted_event_without_vectors() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:verification-completed"),
        event_type=WorkbenchRagEvalWorkflowEventType.VERIFICATION_COMPLETED.value,
        workflow_run_id="run-1",
        payload={
            "workflow_run_id": "run-1",
            "rag_eval_run_id": "run-1",
            "project_id": "project-1",
            "revision_id": "revision-1",
            "runtime_entry_id": "runtime-entry-1",
            "phase": "POST_PROMOTION_VERIFICATION",
            "status": "completed",
            "processed_count": 3,
            "new_embedding": [0.1, 0.2],
        },
        occurred_at=datetime(2026, 7, 14, 12, tzinfo=timezone.utc),
        sequence_number=42,
    )

    projected = WorkbenchRagEvalFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "rag_eval_verification_completed"
    assert projected.document_id == "rag-eval:project-1:run-1"
    assert projected.payload["revision_id"] == "revision-1"
    assert "new_embedding" not in projected.payload
    assert projected.projection_event_id.endswith(":rag_eval_verification_completed:v1")


def test_rag_eval_projector_ignores_unknown_events() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:other"),
        event_type="OtherEvent",
        workflow_run_id="run-1",
        payload={"project_id": "project-1"},
        occurred_at=datetime(2026, 7, 14, 12, tzinfo=timezone.utc),
        sequence_number=1,
    )

    assert WorkbenchRagEvalFrontendWorkflowEventProjector().project(event) is None
