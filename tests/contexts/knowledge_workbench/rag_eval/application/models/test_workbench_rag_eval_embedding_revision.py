from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionStatus,
    WorkbenchRagEvalPromotionApplicationCandidate,
    WorkbenchRagEvalPromotionApplicationClaim,
    WorkbenchRagEvalPromotionApplicationClaimStatus,
    WorkbenchRagEvalPromotionApplicationSnapshot,
    stable_promotion_application_key,
    stable_runtime_snapshot_hash,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
VECTOR_384 = (0.0,) * WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS


def _revision(
    *,
    status: WorkbenchRagEvalEmbeddingRevisionStatus = (
        WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION
    ),
    previous_embedding: tuple[float, ...] = VECTOR_384,
    new_embedding: tuple[float, ...] = VECTOR_384,
    embedding_dimensions: int = WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    previous_questions: tuple[str, ...] = ("Existing?",),
    new_questions: tuple[str, ...] = ("Existing?", "New?"),
    accepted_at: datetime | None = None,
    regression_failed_at: datetime | None = None,
    rolled_back_at: datetime | None = None,
) -> WorkbenchRagEvalEmbeddingRevision:
    return WorkbenchRagEvalEmbeddingRevision(
        revision_id="revision-1",
        project_id="project-1",
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=("promotion-1",),
        status=status,
        previous_embedding_text="old text",
        new_embedding_text="new text",
        previous_embedding=previous_embedding,
        new_embedding=new_embedding,
        previous_promoted_questions=previous_questions,
        new_promoted_questions=new_questions,
        embedding_model_id="model-1",
        embedding_dimensions=embedding_dimensions,
        previous_runtime_hash="old-hash",
        new_runtime_hash="new-hash",
        created_at=NOW,
        accepted_at=accepted_at,
        regression_failed_at=regression_failed_at,
        rolled_back_at=rolled_back_at,
    )


def _snapshot(
    *,
    embedding_dimensions: int = WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
) -> WorkbenchRagEvalPromotionApplicationSnapshot:
    embedding = (
        VECTOR_384
        if embedding_dimensions == WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
        else (0.0,) * embedding_dimensions
    )
    possible_questions = ("Existing?",)
    embedding_text = "old text"
    return WorkbenchRagEvalPromotionApplicationSnapshot(
        project_id="project-1",
        runtime_entry_id="entry-1",
        fact_id="fact-1",
        runtime_status="active",
        runtime_visibility="published",
        claim="Claim",
        possible_questions=possible_questions,
        active_promoted_questions=(),
        exclusion_scope=None,
        embedding_text=embedding_text,
        embedding=embedding,
        embedding_model_id="model-1",
        embedding_dimensions=embedding_dimensions,
        candidates=(
            WorkbenchRagEvalPromotionApplicationCandidate(
                promotion_id="promotion-1",
                run_id="run-1",
                question_id="question-1",
                target_fact_id="fact-1",
                question="New?",
                status=WorkbenchRagEvalPromotionStatus.APPROVED,
            ),
        ),
        runtime_hash=(
            stable_runtime_snapshot_hash(
                possible_questions=possible_questions,
                embedding_text=embedding_text,
                embedding=embedding,
                embedding_model_id="model-1",
                embedding_dimensions=embedding_dimensions,
            )
            if embedding_dimensions == WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
            else "invalid-dimensions"
        ),
        active_revision_id=None,
    )


def test_pending_revision_accepts_canonical_384_dimension_snapshot() -> None:
    revision = _revision()
    assert revision.embedding_dimensions == WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
    assert len(revision.new_embedding) == WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS


def test_revision_rejects_non_canonical_dimensions() -> None:
    with pytest.raises(ValueError, match="must equal 384"):
        _revision(
            previous_embedding=(0.0,) * 3,
            new_embedding=(0.0,) * 3,
            embedding_dimensions=3,
        )


def test_snapshot_rejects_non_canonical_dimensions() -> None:
    with pytest.raises(ValueError, match="must equal 384"):
        _snapshot(embedding_dimensions=3)


def test_stable_runtime_hash_rejects_non_canonical_dimensions() -> None:
    with pytest.raises(ValueError, match="must equal 384"):
        stable_runtime_snapshot_hash(
            possible_questions=("Existing?",),
            embedding_text="old text",
            embedding=(0.0,) * 3,
            embedding_model_id="model-1",
            embedding_dimensions=3,
        )


def test_revision_rejects_duplicate_normalized_questions() -> None:
    with pytest.raises(ValueError, match="unique normalized"):
        _revision(new_questions=("How?", " HOW!!! "))


@pytest.mark.parametrize(
    ("status", "accepted_at", "regression_failed_at", "rolled_back_at"),
    [
        (WorkbenchRagEvalEmbeddingRevisionStatus.ACCEPTED, None, None, None),
        (
            WorkbenchRagEvalEmbeddingRevisionStatus.REGRESSION_FAILED,
            None,
            None,
            None,
        ),
        (WorkbenchRagEvalEmbeddingRevisionStatus.ROLLED_BACK, None, None, None),
    ],
)
def test_terminal_revision_status_requires_matching_timestamp(
    status: WorkbenchRagEvalEmbeddingRevisionStatus,
    accepted_at: datetime | None,
    regression_failed_at: datetime | None,
    rolled_back_at: datetime | None,
) -> None:
    with pytest.raises(ValueError, match="requires"):
        _revision(
            status=status,
            accepted_at=accepted_at,
            regression_failed_at=regression_failed_at,
            rolled_back_at=rolled_back_at,
        )


def test_pending_revision_rejects_terminal_timestamp() -> None:
    with pytest.raises(ValueError, match="cannot have terminal timestamps"):
        _revision(accepted_at=NOW)


def test_stable_application_key_is_order_independent_for_promotions() -> None:
    first = stable_promotion_application_key(
        project_id="project-1",
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=("promotion-2", "promotion-1"),
        previous_runtime_hash="hash-1",
    )
    second = stable_promotion_application_key(
        project_id="project-1",
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=("promotion-1", "promotion-2"),
        previous_runtime_hash="hash-1",
    )
    assert first == second


def test_claim_state_contract_rejects_completed_without_revision() -> None:
    with pytest.raises(ValueError, match="requires revision_id"):
        WorkbenchRagEvalPromotionApplicationClaim(
            application_key="application-1",
            project_id="project-1",
            runtime_entry_id="entry-1",
            source_rag_eval_run_id="run-1",
            promotion_ids=("promotion-1",),
            previous_runtime_hash="hash-1",
            status=WorkbenchRagEvalPromotionApplicationClaimStatus.COMPLETED,
            lease_owner="owner-1",
            lease_expires_at=NOW + timedelta(minutes=5),
            revision_id=None,
            created_at=NOW,
            updated_at=NOW,
            completed_at=NOW,
        )
