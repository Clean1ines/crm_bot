from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_embedding_frontend_workflow_event_projector import (
    DraftClaimEmbeddingBatchCompletedFrontendWorkflowEventProjector,
    DraftClaimEmbeddingFrontendWorkflowEventProjector,
    DraftClaimEmbeddingsGeneratedFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)

_EMBEDDING_PAYLOAD_KEYS = frozenset(
    {
        "workflow_run_id",
        "requested_count",
        "persisted_count",
        "already_exists_count",
        "embedding_model_id",
        "dimensions",
    }
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _canonical_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "operation_key": "generate_draft_claim_embeddings",
        "canonical_phase": KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_EMBEDDING.value,
        "requested_count": 2,
        "persisted_count": 2,
        "already_exists_count": 0,
        "embedding_model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "dimensions": 384,
        "next_run_after": _now().isoformat(),
        "next_command_type": "ClusterDraftClaims",
    }


def _batch_event(*, payload: dict[str, object] | None = None) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{_workflow_run_id()}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED.value}:"
            "workflow-command:embeddings:batch-completed"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED.value
        ),
        workflow_run_id=_workflow_run_id(),
        payload=payload or _canonical_payload(),
        occurred_at=_now(),
        sequence_number=61,
    )


def _generated_event(*, payload: dict[str, object] | None = None) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{_workflow_run_id()}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED.value}:"
            "workflow-command:embeddings:generated"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED.value
        ),
        workflow_run_id=_workflow_run_id(),
        payload=payload or _canonical_payload(),
        occurred_at=_now(),
        sequence_number=62,
    )


def test_projects_batch_completed_to_versioned_envelope() -> None:
    projected = (
        DraftClaimEmbeddingBatchCompletedFrontendWorkflowEventProjector().project(
            _batch_event()
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_embedding_batch_completed"
    assert projected.operation_key == "generate_draft_claim_embeddings"
    assert projected.canonical_phase == (
        KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_EMBEDDING.value
    )
    assert (
        projected.projection_event_id == "frontend-workflow-event:"
        f"{_batch_event().event_id.value}:"
        "workflow_draft_claim_embedding_batch_completed:v1"
    )


def test_projects_embeddings_generated_to_versioned_envelope() -> None:
    projected = DraftClaimEmbeddingsGeneratedFrontendWorkflowEventProjector().project(
        _generated_event()
    )

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_embeddings_generated"
    assert projected.operation_key == "generate_draft_claim_embeddings"
    assert projected.canonical_phase == (
        KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_EMBEDDING.value
    )


def test_router_projects_batch_completed() -> None:
    projected = DraftClaimEmbeddingFrontendWorkflowEventProjector().project(
        _batch_event()
    )

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_embedding_batch_completed"


def test_router_projects_embeddings_generated() -> None:
    projected = DraftClaimEmbeddingFrontendWorkflowEventProjector().project(
        _generated_event()
    )

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_embeddings_generated"


def test_ignores_unsupported_workflow_event() -> None:
    projected = DraftClaimEmbeddingFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
            workflow_run_id=_workflow_run_id(),
            payload={"workflow_run_id": _workflow_run_id()},
            occurred_at=_now(),
            sequence_number=1,
        )
    )

    assert projected is None


@pytest.mark.parametrize("missing_key", ("operation_key", "canonical_phase"))
@pytest.mark.parametrize(
    "projector_factory",
    (
        DraftClaimEmbeddingBatchCompletedFrontendWorkflowEventProjector,
        DraftClaimEmbeddingsGeneratedFrontendWorkflowEventProjector,
    ),
)
def test_requires_explicit_envelope_fields_in_payload(
    missing_key: str,
    projector_factory: type[
        DraftClaimEmbeddingBatchCompletedFrontendWorkflowEventProjector
        | DraftClaimEmbeddingsGeneratedFrontendWorkflowEventProjector
    ],
) -> None:
    payload = _canonical_payload()
    del payload[missing_key]
    event = (
        _batch_event(payload=payload)
        if projector_factory
        is DraftClaimEmbeddingBatchCompletedFrontendWorkflowEventProjector
        else _generated_event(payload=payload)
    )

    with pytest.raises(ValueError, match=missing_key):
        projector_factory().project(event)


def test_projection_payload_is_allowlist_only() -> None:
    projected = (
        DraftClaimEmbeddingBatchCompletedFrontendWorkflowEventProjector().project(
            _batch_event()
        )
    )

    assert projected is not None
    assert set(projected.payload) == _EMBEDDING_PAYLOAD_KEYS
    assert projected.payload["requested_count"] == 2
    assert projected.payload["persisted_count"] == 2


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "operation_key",
        "canonical_phase",
        "next_run_after",
        "next_command_type",
    ),
)
def test_projection_excludes_forbidden_payload_fields(forbidden_key: str) -> None:
    projected = DraftClaimEmbeddingsGeneratedFrontendWorkflowEventProjector().project(
        _generated_event()
    )

    assert projected is not None
    assert forbidden_key not in projected.payload
