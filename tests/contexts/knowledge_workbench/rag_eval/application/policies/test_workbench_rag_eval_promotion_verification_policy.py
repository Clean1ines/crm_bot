from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_verification import (
    WorkbenchRagEvalVerificationDatasetRole,
    WorkbenchRagEvalVerificationDecision,
    WorkbenchRagEvalVerificationFailureReason,
    WorkbenchRagEvalVerificationMetrics,
    WorkbenchRagEvalVerificationOutcomePair,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalRetrievalClassification,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_verification_policy import (
    WorkbenchRagEvalPromotionVerificationPolicy,
)


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def _pair(
    *,
    role: WorkbenchRagEvalVerificationDatasetRole,
    before_rank: int | None,
    after_rank: int | None,
    before_margin: float | None = 0.1,
    after_margin: float | None = 0.2,
    expected_runtime_entry_id: str = "target-entry",
    before_best_competitor_runtime_entry_id: str | None = "other-entry",
    after_best_competitor_runtime_entry_id: str | None = "other-entry",
) -> WorkbenchRagEvalVerificationOutcomePair:
    return WorkbenchRagEvalVerificationOutcomePair(
        verification_query_id=f"vq-{role.value}",
        dataset_role=role,
        expected_runtime_entry_id=expected_runtime_entry_id,
        before_expected_rank=before_rank,
        after_expected_rank=after_rank,
        before_expected_score=0.5 if before_rank is not None else None,
        after_expected_score=0.8 if after_rank is not None else None,
        before_best_competitor_runtime_entry_id=before_best_competitor_runtime_entry_id,
        after_best_competitor_runtime_entry_id=after_best_competitor_runtime_entry_id,
        before_score_margin=before_margin,
        after_score_margin=after_margin,
        before_classification=(
            WorkbenchRagEvalRetrievalClassification.MISS
            if before_rank is None
            else WorkbenchRagEvalRetrievalClassification.PASS_WEAK
        ),
        after_classification=(
            WorkbenchRagEvalRetrievalClassification.MISS
            if after_rank is None
            else WorkbenchRagEvalRetrievalClassification.PASS_WEAK
        ),
    )


def test_metrics_calculation_is_finite_and_exact_for_empty_optional_roles() -> None:
    metrics = WorkbenchRagEvalVerificationMetrics.from_outcome_pairs(
        (
            _pair(
                role=WorkbenchRagEvalVerificationDatasetRole.PROMOTED,
                before_rank=None,
                after_rank=2,
            ),
            _pair(
                role=WorkbenchRagEvalVerificationDatasetRole.HOLDOUT,
                before_rank=2,
                after_rank=2,
                before_margin=0.4,
                after_margin=0.4,
            ),
        )
    )

    assert metrics.overall.query_count == 2
    assert metrics.overall.top3_rate == 1.0
    assert metrics.promoted.promoted_top3_improvement_count == 1
    assert metrics.promoted.promoted_top3_regression_count == 0
    assert metrics.holdout.holdout_top3_recall_delta == 0.0
    assert metrics.baseline.query_count == 0
    assert metrics.neighbour.neighbor_top1_regression_count == 0
    assert metrics.neighbour.top3_rate == 0.0


def test_policy_accepts_promoted_improvement_without_regressions() -> None:
    metrics = WorkbenchRagEvalVerificationMetrics.from_outcome_pairs(
        (
            _pair(
                role=WorkbenchRagEvalVerificationDatasetRole.PROMOTED,
                before_rank=None,
                after_rank=2,
            ),
            _pair(
                role=WorkbenchRagEvalVerificationDatasetRole.HOLDOUT,
                before_rank=1,
                after_rank=1,
            ),
            _pair(
                role=WorkbenchRagEvalVerificationDatasetRole.BASELINE,
                before_rank=2,
                after_rank=2,
            ),
            _pair(
                role=WorkbenchRagEvalVerificationDatasetRole.NEIGHBOUR,
                before_rank=1,
                after_rank=1,
                expected_runtime_entry_id="neighbour-entry",
                before_best_competitor_runtime_entry_id="target-entry",
                after_best_competitor_runtime_entry_id="target-entry",
            ),
        )
    )

    decision = WorkbenchRagEvalPromotionVerificationPolicy().decide(metrics)

    assert decision.decision is WorkbenchRagEvalVerificationDecision.ACCEPTABLE
    assert decision.failure_reasons == ()


@pytest.mark.parametrize(
    ("pairs", "expected_reason"),
    [
        (
            (
                _pair(
                    role=WorkbenchRagEvalVerificationDatasetRole.PROMOTED,
                    before_rank=2,
                    after_rank=4,
                ),
            ),
            WorkbenchRagEvalVerificationFailureReason.PROMOTED_TOP3_REGRESSION,
        ),
        (
            (
                _pair(
                    role=WorkbenchRagEvalVerificationDatasetRole.HOLDOUT,
                    before_rank=2,
                    after_rank=None,
                ),
            ),
            WorkbenchRagEvalVerificationFailureReason.HOLDOUT_TOP3_RECALL_REGRESSION,
        ),
        (
            (
                _pair(
                    role=WorkbenchRagEvalVerificationDatasetRole.BASELINE,
                    before_rank=3,
                    after_rank=None,
                ),
            ),
            WorkbenchRagEvalVerificationFailureReason.BASELINE_TOP3_RECALL_REGRESSION,
        ),
        (
            (
                _pair(
                    role=WorkbenchRagEvalVerificationDatasetRole.NEIGHBOUR,
                    before_rank=1,
                    after_rank=2,
                    before_best_competitor_runtime_entry_id="other-entry",
                    after_best_competitor_runtime_entry_id="target-entry",
                ),
            ),
            WorkbenchRagEvalVerificationFailureReason.NEIGHBOUR_TOP1_REGRESSION,
        ),
    ],
)
def test_policy_reports_structured_regression_reasons(
    pairs: tuple[WorkbenchRagEvalVerificationOutcomePair, ...],
    expected_reason: WorkbenchRagEvalVerificationFailureReason,
) -> None:
    metrics = WorkbenchRagEvalVerificationMetrics.from_outcome_pairs(pairs)

    decision = WorkbenchRagEvalPromotionVerificationPolicy().decide(metrics)

    assert decision.decision is WorkbenchRagEvalVerificationDecision.REGRESSION
    assert expected_reason in decision.failure_reasons


def test_policy_rejects_invalid_empty_promoted_dataset() -> None:
    metrics = WorkbenchRagEvalVerificationMetrics.from_outcome_pairs(
        (
            _pair(
                role=WorkbenchRagEvalVerificationDatasetRole.HOLDOUT,
                before_rank=1,
                after_rank=1,
            ),
        )
    )

    decision = WorkbenchRagEvalPromotionVerificationPolicy().decide(metrics)

    assert decision.decision is WorkbenchRagEvalVerificationDecision.REGRESSION
    assert (
        WorkbenchRagEvalVerificationFailureReason.EMPTY_PROMOTED_DATASET
        in decision.failure_reasons
    )
