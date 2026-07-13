from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionStatus,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _revision(
    *,
    status: WorkbenchRagEvalEmbeddingRevisionStatus = (
        WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION
    ),
    previous_embedding: tuple[float, ...] = (0.1, 0.2, 0.3),
    new_embedding: tuple[float, ...] = (0.4, 0.5, 0.6),
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
        embedding_dimensions=3,
        previous_runtime_hash="old-hash",
        new_runtime_hash="new-hash",
        created_at=NOW,
        accepted_at=accepted_at,
        regression_failed_at=regression_failed_at,
        rolled_back_at=rolled_back_at,
    )


def test_pending_revision_accepts_complete_snapshot_without_terminal_timestamps() -> (
    None
):
    revision = _revision()
    assert (
        revision.status is WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION
    )


@pytest.mark.parametrize(
    ("previous_embedding", "new_embedding"),
    [
        ((0.1, 0.2), (0.4, 0.5, 0.6)),
        ((0.1, 0.2, 0.3), (0.4, 0.5)),
    ],
)
def test_revision_rejects_vector_dimension_mismatch(
    previous_embedding: tuple[float, ...],
    new_embedding: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        _revision(
            previous_embedding=previous_embedding,
            new_embedding=new_embedding,
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
