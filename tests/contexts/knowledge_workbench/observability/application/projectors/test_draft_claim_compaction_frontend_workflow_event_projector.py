from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_compaction_frontend_workflow_event_projector import (
    DraftClaimCompactionFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def test_projects_compaction_blocked_event_to_frontend_projection() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{_workflow_run_id()}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED.value}:"
            "workflow-command:reconcile"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED.value
        ),
        workflow_run_id=_workflow_run_id(),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "reason": "terminal_execution_failure",
            "group_counters": {
                "group_count": 2,
                "done_group_count": 1,
                "active_group_count": 1,
            },
            "execution_counters": {
                "total_count": 2,
                "terminal_failed_count": 1,
            },
            "next_due_at": None,
        },
        occurred_at=_now(),
        sequence_number=72,
    )

    projected = DraftClaimCompactionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == (
        "workflow_draft_claim_compaction_progress_blocked"
    )
    assert projected.operation_key == "draft_claim_compaction"
    assert projected.canonical_phase == (
        KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
    )
    assert projected.payload["reason"] == "terminal_execution_failure"
    assert projected.payload["group_counters"] == {
        "group_count": 2,
        "done_group_count": 1,
        "active_group_count": 1,
    }
    assert projected.payload["execution_counters"] == {
        "total_count": 2,
        "terminal_failed_count": 1,
    }
