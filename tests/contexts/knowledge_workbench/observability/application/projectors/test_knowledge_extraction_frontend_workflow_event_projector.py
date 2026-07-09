from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_frontend_workflow_event_projector import (
    ClaimBuilderFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_cluster_frontend_workflow_event_projector import (
    DraftClaimClusterFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_curation_frontend_workflow_event_projector import (
    DraftClaimCurationFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_embedding_frontend_workflow_event_projector import (
    DraftClaimEmbeddingFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.knowledge_extraction_frontend_workflow_event_projector import (
    KnowledgeExtractionFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.source_ingestion_frontend_workflow_event_projector import (
    SourceIngestionFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def test_workflow_composite_routes_claim_builder_progress_event() -> None:
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
            "summary": {"ready_count": 1, "total_count": 1},
        },
        occurred_at=_now(),
        sequence_number=7,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_claim_builder_progress_reconciled"


def test_workflow_composite_routes_embedding_batch_completed_event() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:embedding-batch"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "generate_draft_claim_embeddings",
            "canonical_phase": "DRAFT_CLAIM_EMBEDDING",
            "requested_count": 1,
            "persisted_count": 1,
            "already_exists_count": 0,
            "embedding_model_id": "sentence-transformers/all-MiniLM-L6-v2",
            "dimensions": 384,
        },
        occurred_at=_now(),
        sequence_number=8,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_embedding_batch_completed"


def test_workflow_composite_routes_embedding_generated_event() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:embedding-generated"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "generate_draft_claim_embeddings",
            "canonical_phase": "DRAFT_CLAIM_EMBEDDING",
            "requested_count": 1,
            "persisted_count": 1,
            "already_exists_count": 0,
            "embedding_model_id": "sentence-transformers/all-MiniLM-L6-v2",
            "dimensions": 384,
        },
        occurred_at=_now(),
        sequence_number=9,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_embeddings_generated"


def test_workflow_composite_routes_clusters_built_event() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:clusters-built"),
        event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "cluster_draft_claims",
            "canonical_phase": "DRAFT_CLAIM_CLUSTERING",
            "candidate_edge_count": 1,
            "group_count": 1,
            "batch_count": 1,
            "scheduled_work_item_count": 1,
            "semantic_meaning": "build hybrid draft claim compaction plan",
        },
        occurred_at=_now(),
        sequence_number=10,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_clusters_built"


def test_workflow_composite_routes_compaction_dispatch_prepared_event() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:compaction-dispatch-prepared"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "work_kind": "knowledge_workbench.draft_claim_compaction",
            "dispatch_attempt_ids": ["attempt-1"],
            "work_item_ids": ["work-item-1"],
            "dispatch_contexts": [
                {
                    "dispatch_attempt_id": "attempt-1",
                    "work_item_id": "work-item-1",
                    "group_ref": "group-1",
                    "batch_ref": "batch-1",
                }
            ],
        },
        occurred_at=_now(),
        sequence_number=11,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert (
        projected.projection_type
        == "workflow_draft_claim_compaction_dispatch_batch_prepared"
    )
    assert projected.operation_key == "prepare_draft_claim_compaction_dispatch_batch"
    assert projected.canonical_phase == "DRAFT_CLAIM_CLUSTERING"


def test_workflow_composite_routes_curation_workspace_opened_event() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:curation-opened"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_OPENED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workspace_ref": "draft-claim-curation-workspace:workflow-1",
            "item_count": 9,
        },
        occurred_at=_now(),
        sequence_number=14,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_curation_workspace_opened"
    assert projected.operation_key == "draft_claim_curation"
    assert projected.canonical_phase == "DRAFT_CLAIM_CURATION"
    assert projected.project_id == "project-1"
    assert projected.document_id == "source-document:project-1:abc"
    assert projected.payload["workflow_run_id"] == event.workflow_run_id
    assert (
        projected.payload["workspace_ref"]
        == "draft-claim-curation-workspace:workflow-1"
    )
    assert projected.payload["item_count"] == 9


def test_workflow_composite_routes_curation_review_required_event() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:curation-review-required"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_REVIEW_REQUIRED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workspace_ref": "draft-claim-curation-workspace:workflow-1",
            "item_count": 9,
        },
        occurred_at=_now(),
        sequence_number=15,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_curation_review_required"
    assert projected.operation_key == "draft_claim_curation"
    assert projected.canonical_phase == "DRAFT_CLAIM_CURATION"


def test_workflow_composite_routes_manual_pause_event() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:manual-pause"),
        event_type=KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_PAUSED.value,
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "project_id": "project-1",
            "source_document_ref": "source-document:project-1:abc",
            "actor_user_id": "owner-1",
            "reason": "manual_pause",
        },
        occurred_at=_now(),
        sequence_number=17,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_manually_paused"
    assert projected.event_type == "WorkflowManuallyPaused"
    assert projected.project_id == "project-1"
    assert projected.document_id == "source-document:project-1:abc"
    assert projected.payload["workflow_status"] == "paused"
    assert projected.payload["timer_mode"] == "paused"
    assert projected.payload["timer_is_live"] is False


def test_workflow_composite_routes_manual_resume_event() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:manual-resume"),
        event_type=KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_RESUMED.value,
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "project_id": "project-1",
            "source_document_ref": "source-document:project-1:abc",
            "actor_user_id": "owner-1",
        },
        occurred_at=_now(),
        sequence_number=18,
    )

    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_manually_resumed"
    assert projected.event_type == "WorkflowManuallyResumed"
    assert projected.project_id == "project-1"
    assert projected.document_id == "source-document:project-1:abc"
    assert projected.payload["workflow_status"] == "running"
    assert projected.payload["timer_mode"] == "running"
    assert projected.payload["timer_is_live"] is True


def test_curation_projector_is_curation_scoped() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:clusters-built-for-curation-scope"),
        event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "cluster_draft_claims",
            "canonical_phase": "DRAFT_CLAIM_CLUSTERING",
            "candidate_edge_count": 1,
            "group_count": 1,
            "batch_count": 1,
            "scheduled_work_item_count": 1,
        },
        occurred_at=_now(),
        sequence_number=16,
    )

    assert DraftClaimCurationFrontendWorkflowEventProjector().project(event) is None


def test_workflow_composite_ignores_truly_unsupported_event() -> None:
    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type="UnsupportedKnowledgeExtractionEvent",
            workflow_run_id="knowledge-extraction:source-document:project-1:abc",
            payload={
                "workflow_run_id": "knowledge-extraction:source-document:project-1:abc"
            },
            occurred_at=_now(),
            sequence_number=12,
        )
    )

    assert projected is None


def test_claim_builder_composite_returns_none_for_clusters_built() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:clusters-built"),
        event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "cluster_draft_claims",
            "canonical_phase": "DRAFT_CLAIM_CLUSTERING",
            "candidate_edge_count": 1,
            "group_count": 1,
            "batch_count": 1,
            "scheduled_work_item_count": 1,
            "semantic_meaning": "build hybrid draft claim compaction plan",
        },
        occurred_at=_now(),
        sequence_number=12,
    )

    assert ClaimBuilderFrontendWorkflowEventProjector().project(event) is None


def test_embedding_composite_returns_none_for_clusters_built() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:clusters-built"),
        event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "cluster_draft_claims",
            "canonical_phase": "DRAFT_CLAIM_CLUSTERING",
            "candidate_edge_count": 1,
            "group_count": 1,
            "batch_count": 1,
            "scheduled_work_item_count": 1,
            "semantic_meaning": "build hybrid draft claim compaction plan",
        },
        occurred_at=_now(),
        sequence_number=13,
    )

    assert DraftClaimEmbeddingFrontendWorkflowEventProjector().project(event) is None
    assert DraftClaimClusterFrontendWorkflowEventProjector().project(event) is not None


def test_claim_builder_composite_remains_claim_builder_scoped() -> None:
    event = WorkflowEvent(
        event_id=WorkflowEventId("workflow-event:embedding-generated"),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED.value
        ),
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        payload={
            "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
            "operation_key": "generate_draft_claim_embeddings",
            "canonical_phase": "DRAFT_CLAIM_EMBEDDING",
            "requested_count": 1,
            "persisted_count": 1,
            "already_exists_count": 0,
            "embedding_model_id": "sentence-transformers/all-MiniLM-L6-v2",
            "dimensions": 384,
        },
        occurred_at=_now(),
        sequence_number=11,
    )

    assert ClaimBuilderFrontendWorkflowEventProjector().project(event) is None
    assert (
        DraftClaimEmbeddingFrontendWorkflowEventProjector().project(event) is not None
    )
    assert SourceIngestionFrontendWorkflowEventProjector().project(event) is None
