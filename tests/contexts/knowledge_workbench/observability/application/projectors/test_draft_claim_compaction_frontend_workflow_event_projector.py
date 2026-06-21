from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_compaction_frontend_workflow_event_projector import (
    DraftClaimCompactionFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


ROOT = Path(__file__).resolve().parents[6]


def _event(event_type: str, payload: dict[str, object]) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(f"workflow-event:test:{event_type}"),
        event_type=event_type,
        workflow_run_id=str(payload.get("workflow_run_id", "workflow-1")),
        payload=payload,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        sequence_number=7,
    )


def test_completed_attempt_projects_sanitized_attempt_outcome() -> None:
    projected = DraftClaimCompactionFrontendWorkflowEventProjector().project(
        _event(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED.value,
            {
                "workflow_run_id": "workflow-1",
                "work_item_id": "claim-compaction:workflow-1:batch-1",
                "dispatch_attempt_id": "attempt-1",
                "work_kind": "knowledge_workbench.draft_claim_compaction",
                "outcome_status": "succeeded",
                "provider": "groq",
                "account_ref": "account-1",
                "model_ref": "model-1",
                "actual_prompt_tokens": 11,
                "actual_completion_tokens": 13,
                "actual_total_tokens": 24,
                "draft_claim_compaction_validation_decision": "valid_output",
                "expected_output_kind": "compacted_claims",
                "validated_compacted_claim_count": 2,
            },
        )
    )

    assert projected is not None
    outcome = projected.payload["attempt_outcome"]
    assert (
        projected.projection_type == "workflow_draft_claim_compaction_attempt_completed"
    )
    assert outcome["attempt_scope"]["dispatch_attempt_id"] == "attempt-1"
    assert outcome["attempt_scope"]["batch_ref"] == "batch-1"
    assert outcome["provider_outcome"]["total_tokens"] == 24
    assert outcome["validation_outcome"]["expected_output_kind"] == "compacted_node"
    assert outcome["work_item_outcome"]["completed"] is True
    assert outcome["result_pointer"]["result_applied"] is False
    assert outcome["result_pointer"]["generated_nodes_available"] is False
    assert outcome["capacity_annotation"]["capacity_window_owned"] is True


@pytest.mark.parametrize(
    ("event_type", "projection_type", "state"),
    [
        (
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_RETRYABLE_FAILED.value,
            "workflow_draft_claim_compaction_attempt_retryable_failed",
            "retryable_failed",
        ),
        (
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_TERMINAL_FAILED.value,
            "workflow_draft_claim_compaction_attempt_terminal_failed",
            "terminal_failed",
        ),
    ],
)
def test_retryable_and_terminal_attempts_do_not_expose_generated_nodes(
    event_type: str,
    projection_type: str,
    state: str,
) -> None:
    projected = DraftClaimCompactionFrontendWorkflowEventProjector().project(
        _event(
            event_type,
            {
                "workflow_run_id": "workflow-1",
                "work_item_id": "claim-compaction:workflow-1:batch-1",
                "dispatch_attempt_id": "attempt-1",
                "outcome_status": "retryable_failed",
                "error_kind": "provider_error",
                "next_attempt_at": "2026-01-01T00:00:00+00:00",
            },
        )
    )

    assert projected is not None
    assert projected.projection_type == projection_type
    outcome = projected.payload["attempt_outcome"]
    assert outcome["work_item_outcome"]["work_item_state"] == state
    assert outcome["result_pointer"]["generated_nodes_available"] is False
    assert "next_attempt_at" not in str(projected.payload)
    assert "provider_reset_at" not in str(projected.payload)


def test_attempt_projection_excludes_heavy_output_bodies() -> None:
    projected = DraftClaimCompactionFrontendWorkflowEventProjector().project(
        _event(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED.value,
            {
                "workflow_run_id": "workflow-1",
                "work_item_id": "claim-compaction:workflow-1:batch-1",
                "dispatch_attempt_id": "attempt-1",
                "outcome_status": "succeeded",
                "expected_output_kind": "compacted_claims",
                "compacted_claims": [{"claim": "body", "triples": []}],
                "reduced_rewrite": {"claim": "body", "triples": []},
                "claim": "body",
                "possible_questions": ["q"],
                "exclusion_scope": "scope",
                "evidence_block": "evidence",
                "source_claim_refs": ["obs-1"],
                "target_claim_refs": ["node-1"],
                "raw_output": "raw",
                "parsed_output": {"claim": "body"},
                "model_output": "body",
                "messages": [{"role": "assistant", "content": "body"}],
            },
        )
    )

    assert projected is not None
    payload_text = str(projected.payload)
    for forbidden in (
        "compacted_claims",
        "reduced_rewrite",
        "possible_questions",
        "exclusion_scope",
        "evidence_block",
        "source_claim_refs",
        "target_claim_refs",
        "raw_output",
        "parsed_output",
        "model_output",
        "messages",
    ):
        assert forbidden not in payload_text


def test_result_applied_exposes_generated_node_targeted_read() -> None:
    projected = DraftClaimCompactionFrontendWorkflowEventProjector().project(
        _event(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value,
            {
                "workflow_run_id": "workflow-1",
                "group_ref": "group-1",
                "batch_ref": "batch-1",
                "work_item_id": "claim-compaction:workflow-1:batch-1",
                "created_node_refs": ["node-1"],
                "superseded_node_refs": ["raw-1"],
                "comparison_refs": ["comparison-1"],
                "next_work_type": "done",
            },
        )
    )

    assert projected is not None
    nodes = projected.payload["generated_compaction_nodes"]
    assert nodes["surface_kind"] == "draft_claim_compaction_node"
    assert nodes["availability"] == "available"
    assert nodes["parent_scope"]["group_ref"] == "group-1"
    assert nodes["parent_scope"]["batch_ref"] == "batch-1"
    assert (
        nodes["targeted_read"]["kind"]
        == "draft_claim_compaction_nodes_by_workflow_or_group"
    )
    assert nodes["targeted_read"]["params"]["active_only"] is False
    assert nodes["created_node_refs"] == ["node-1"]


def test_reduced_rewrite_ref_gap_uses_targeted_read_scope() -> None:
    projected = DraftClaimCompactionFrontendWorkflowEventProjector().project(
        _event(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value,
            {
                "workflow_run_id": "workflow-1",
                "group_ref": "group-1",
                "batch_ref": "batch-1",
                "work_item_id": "claim-compaction:workflow-1:batch-1",
                "created_node_refs": [],
                "superseded_node_refs": ["node-a", "node-b"],
                "comparison_refs": ["comparison-1"],
                "next_work_type": "done",
            },
        )
    )

    assert projected is not None
    nodes = projected.payload["generated_compaction_nodes"]
    assert (
        nodes["created_node_ref_gap"] == "result_applied_event_has_no_created_node_refs"
    )
    assert nodes["targeted_read"]["params"]["group_ref"] == "group-1"


def test_next_work_scheduled_does_not_invent_batch_rows() -> None:
    projected = DraftClaimCompactionFrontendWorkflowEventProjector().project(
        _event(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_NEXT_WORK_SCHEDULED.value,
            {
                "workflow_run_id": "workflow-1",
                "group_ref": "group-1",
                "reason": "more_work",
                "next_work_type": "mixed",
                "scheduled_work_item_count": 1,
                "already_scheduled_work_item_count": 0,
                "appended_next_command_count": 1,
            },
        )
    )

    assert projected is not None
    assert "cluster_batch_rows" not in projected.payload
    assert (
        projected.payload["next_compaction_work"]["does_not_create_cluster_batch_rows"]
        is True
    )


def test_cluster_done_and_all_groups_compacted_are_separate_layers() -> None:
    projector = DraftClaimCompactionFrontendWorkflowEventProjector()
    cluster_done = projector.project(
        _event(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_CLUSTER_DONE.value,
            {"workflow_run_id": "workflow-1", "group_ref": "group-1"},
        )
    )
    all_done = projector.project(
        _event(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ALL_GROUPS_COMPACTED.value,
            {
                "workflow_run_id": "workflow-1",
                "summary": {"done_group_count": 2, "group_count": 2},
                "next_command_type": "OpenDraftClaimCurationWorkspace",
            },
        )
    )

    assert cluster_done is not None
    assert (
        cluster_done.payload["cluster_group_compaction"][
            "document_compaction_completed"
        ]
        is False
    )
    assert all_done is not None
    assert all_done.payload["document_compaction"]["status"] == "completed"
    assert (
        all_done.payload["document_compaction"]["curation_readiness"]
        == "ready_to_open_workspace"
    )
    assert all_done.payload["document_compaction"]["publication_ready"] is False


def test_next_work_scheduled_remains_progress_not_cluster_batch_row() -> None:
    source = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "observability"
        / "application"
        / "projectors"
        / "draft_claim_compaction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert "workflow_draft_claim_compaction_next_work_scheduled" in source
    assert "ClusterBatch" not in source
    assert "generated_compaction_nodes" in source


def test_next_work_scheduled_points_to_pending_reduction_work_read_surface() -> None:
    projected = DraftClaimCompactionFrontendWorkflowEventProjector().project(
        _event(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_NEXT_WORK_SCHEDULED.value,
            {
                "workflow_run_id": "workflow-1",
                "group_ref": "group-1",
                "reason": "more_work",
                "next_work_type": "mixed",
                "scheduled_work_item_count": 1,
                "already_scheduled_work_item_count": 0,
                "appended_next_command_count": 1,
            },
        )
    )

    assert projected is not None
    assert "cluster_batch_rows" not in projected.payload
    assert (
        projected.payload["next_compaction_work"]["does_not_create_cluster_batch_rows"]
        is True
    )
