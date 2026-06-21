from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_frontend_workflow_event_projector import (
    ClaimBuilderFrontendWorkflowEventProjector,
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


def test_workflow_composite_ignores_unsupported_event() -> None:
    projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
            workflow_run_id="knowledge-extraction:source-document:project-1:abc",
            payload={
                "workflow_run_id": "knowledge-extraction:source-document:project-1:abc"
            },
            occurred_at=_now(),
            sequence_number=10,
        )
    )

    assert projected is None


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
