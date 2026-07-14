from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_verification import (
    WORKBENCH_RAG_EVAL_VERIFICATION_POLICY_VERSION,
    WorkbenchRagEvalVerificationDecision,
    WorkbenchRagEvalVerificationFailureReason,
    WorkbenchRagEvalVerificationMetrics,
    WorkbenchRagEvalVerificationPolicyDecision,
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionVerificationPolicyConfig:
    version: str = WORKBENCH_RAG_EVAL_VERIFICATION_POLICY_VERSION
    minimum_promoted_top3_improvement_count: int = 1
    minimum_promoted_top3_rate_after: float = 0.0
    minimum_promoted_mean_margin_delta: float = 0.0
    minimum_holdout_top3_recall_delta: float = 0.0
    minimum_holdout_mean_margin_delta: float = 0.0
    minimum_baseline_top3_recall_delta: float = 0.0
    maximum_baseline_regression_count: int = 0
    maximum_neighbor_top1_regression_count: int = 0
    maximum_neighbor_top3_regression_count: int = 0
    minimum_overall_mean_margin_delta: float = 0.0

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must be non-empty")
        for field_name in (
            "minimum_promoted_top3_improvement_count",
            "maximum_baseline_regression_count",
            "maximum_neighbor_top1_regression_count",
            "maximum_neighbor_top3_regression_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionVerificationPolicy:
    config: WorkbenchRagEvalPromotionVerificationPolicyConfig = (
        WorkbenchRagEvalPromotionVerificationPolicyConfig()
    )

    def decide(
        self,
        metrics: WorkbenchRagEvalVerificationMetrics,
    ) -> WorkbenchRagEvalVerificationPolicyDecision:
        if not isinstance(metrics, WorkbenchRagEvalVerificationMetrics):
            raise TypeError("metrics must be WorkbenchRagEvalVerificationMetrics")

        reasons: list[WorkbenchRagEvalVerificationFailureReason] = []
        promoted = metrics.promoted
        holdout = metrics.holdout
        baseline = metrics.baseline
        neighbour = metrics.neighbour

        if promoted.query_count == 0:
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.EMPTY_PROMOTED_DATASET
            )
        elif (
            promoted.promoted_top3_improvement_count
            < self.config.minimum_promoted_top3_improvement_count
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.PROMOTED_TOP3_NOT_IMPROVED
            )

        if promoted.top3_rate < self.config.minimum_promoted_top3_rate_after:
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.PROMOTED_TOP3_RATE_REGRESSION
            )
        if promoted.promoted_top3_regression_count > 0:
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.PROMOTED_TOP3_REGRESSION
            )
        if (
            promoted.promoted_mean_margin_delta
            < self.config.minimum_promoted_mean_margin_delta
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.PROMOTED_MARGIN_REGRESSION
            )

        if (
            holdout.query_count > 0
            and holdout.holdout_top3_recall_delta
            < self.config.minimum_holdout_top3_recall_delta
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.HOLDOUT_TOP3_RECALL_REGRESSION
            )
        if (
            holdout.query_count > 0
            and holdout.holdout_mean_margin_delta
            < self.config.minimum_holdout_mean_margin_delta
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.HOLDOUT_MARGIN_REGRESSION
            )

        if (
            baseline.query_count > 0
            and baseline.baseline_top3_recall_delta
            < self.config.minimum_baseline_top3_recall_delta
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.BASELINE_TOP3_RECALL_REGRESSION
            )
        if (
            baseline.baseline_regression_count
            > self.config.maximum_baseline_regression_count
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.BASELINE_REGRESSION
            )

        if (
            neighbour.neighbor_top1_regression_count
            > self.config.maximum_neighbor_top1_regression_count
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.NEIGHBOUR_TOP1_REGRESSION
            )
        if (
            neighbour.neighbor_top3_regression_count
            > self.config.maximum_neighbor_top3_regression_count
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.NEIGHBOUR_TOP3_REGRESSION
            )

        if (
            metrics.overall.mean_score_margin
            < self.config.minimum_overall_mean_margin_delta
        ):
            reasons.append(
                WorkbenchRagEvalVerificationFailureReason.OVERALL_MARGIN_REGRESSION
            )

        unique_reasons = tuple(dict.fromkeys(reasons))
        if unique_reasons:
            return WorkbenchRagEvalVerificationPolicyDecision(
                decision=WorkbenchRagEvalVerificationDecision.REGRESSION,
                failure_reasons=unique_reasons,
            )
        return WorkbenchRagEvalVerificationPolicyDecision(
            decision=WorkbenchRagEvalVerificationDecision.ACCEPTABLE,
            failure_reasons=(),
        )
