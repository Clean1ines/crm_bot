from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalRetrievalClassification,
)
from src.domain.project_plane.json_types import JsonObject


WORKBENCH_RAG_EVAL_VERIFICATION_POLICY_VERSION = (
    "workbench_rag_eval_promotion_verification.v1"
)


class WorkbenchRagEvalVerificationDatasetRole(StrEnum):
    PROMOTED = "promoted"
    HOLDOUT = "holdout"
    BASELINE = "baseline"
    NEIGHBOUR = "neighbour"


class WorkbenchRagEvalVerificationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    REGRESSION_FAILED = "regression_failed"
    FAILED = "failed"


class WorkbenchRagEvalVerificationDecision(StrEnum):
    ACCEPTABLE = "acceptable"
    REGRESSION = "regression"


class WorkbenchRagEvalVerificationFailureReason(StrEnum):
    EMPTY_PROMOTED_DATASET = "empty_promoted_dataset"
    PROMOTED_TOP3_NOT_IMPROVED = "promoted_top3_not_improved"
    PROMOTED_TOP3_RATE_REGRESSION = "promoted_top3_rate_regression"
    PROMOTED_TOP3_REGRESSION = "promoted_top3_regression"
    PROMOTED_MARGIN_REGRESSION = "promoted_margin_regression"
    HOLDOUT_TOP3_RECALL_REGRESSION = "holdout_top3_recall_regression"
    HOLDOUT_MARGIN_REGRESSION = "holdout_margin_regression"
    BASELINE_TOP3_RECALL_REGRESSION = "baseline_top3_recall_regression"
    BASELINE_REGRESSION = "baseline_regression"
    NEIGHBOUR_TOP1_REGRESSION = "neighbour_top1_regression"
    NEIGHBOUR_TOP3_REGRESSION = "neighbour_top3_regression"
    OVERALL_MARGIN_REGRESSION = "overall_margin_regression"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalVerificationQuery:
    verification_query_id: str
    revision_id: str
    run_id: str
    project_id: str
    query_text: str
    dataset_role: WorkbenchRagEvalVerificationDatasetRole
    expected_runtime_entry_id: str
    expected_fact_id: str
    source_runtime_entry_id: str
    question_id: str | None
    source_outcome_id: str | None
    promotion_id: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "verification_query_id",
            "revision_id",
            "run_id",
            "project_id",
            "query_text",
            "expected_runtime_entry_id",
            "expected_fact_id",
            "source_runtime_entry_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if not isinstance(self.dataset_role, WorkbenchRagEvalVerificationDatasetRole):
            raise TypeError(
                "dataset_role must be WorkbenchRagEvalVerificationDatasetRole"
            )
        _require_optional_text(self.question_id, "question_id")
        _require_optional_text(self.source_outcome_id, "source_outcome_id")
        _require_optional_text(self.promotion_id, "promotion_id")
        _require_datetime(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalVerificationOutcomePair:
    verification_query_id: str
    dataset_role: WorkbenchRagEvalVerificationDatasetRole
    expected_runtime_entry_id: str
    before_expected_rank: int | None
    after_expected_rank: int | None
    before_expected_score: float | None
    after_expected_score: float | None
    before_best_competitor_runtime_entry_id: str | None
    after_best_competitor_runtime_entry_id: str | None
    before_score_margin: float | None
    after_score_margin: float | None
    before_classification: WorkbenchRagEvalRetrievalClassification
    after_classification: WorkbenchRagEvalRetrievalClassification

    def __post_init__(self) -> None:
        _require_text(self.verification_query_id, "verification_query_id")
        _require_text(self.expected_runtime_entry_id, "expected_runtime_entry_id")
        if not isinstance(self.dataset_role, WorkbenchRagEvalVerificationDatasetRole):
            raise TypeError(
                "dataset_role must be WorkbenchRagEvalVerificationDatasetRole"
            )
        for field_name in ("before_expected_rank", "after_expected_rank"):
            value = getattr(self, field_name)
            if value is not None:
                _require_positive_int(value, field_name)
        for field_name in (
            "before_expected_score",
            "after_expected_score",
            "before_score_margin",
            "after_score_margin",
        ):
            _require_optional_finite_float(getattr(self, field_name), field_name)
        _require_optional_text(
            self.before_best_competitor_runtime_entry_id,
            "before_best_competitor_runtime_entry_id",
        )
        _require_optional_text(
            self.after_best_competitor_runtime_entry_id,
            "after_best_competitor_runtime_entry_id",
        )
        if not isinstance(
            self.before_classification,
            WorkbenchRagEvalRetrievalClassification,
        ):
            raise TypeError("before_classification must be retrieval classification")
        if not isinstance(
            self.after_classification,
            WorkbenchRagEvalRetrievalClassification,
        ):
            raise TypeError("after_classification must be retrieval classification")

    @property
    def before_top1_hit(self) -> bool:
        return self.before_expected_rank == 1

    @property
    def after_top1_hit(self) -> bool:
        return self.after_expected_rank == 1

    @property
    def before_top3_hit(self) -> bool:
        return self.before_expected_rank is not None and self.before_expected_rank <= 3

    @property
    def after_top3_hit(self) -> bool:
        return self.after_expected_rank is not None and self.after_expected_rank <= 3

    @property
    def before_top5_hit(self) -> bool:
        return self.before_expected_rank is not None and self.before_expected_rank <= 5

    @property
    def after_top5_hit(self) -> bool:
        return self.after_expected_rank is not None and self.after_expected_rank <= 5

    @property
    def margin_delta(self) -> float:
        return _zero_if_none(self.after_score_margin) - _zero_if_none(
            self.before_score_margin
        )


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalVerificationSearchObservation:
    expected_rank: int | None
    expected_score: float | None
    best_competitor_runtime_entry_id: str | None
    best_competitor_fact_id: str | None
    best_competitor_score: float | None
    score_margin: float | None
    classification: WorkbenchRagEvalRetrievalClassification

    def __post_init__(self) -> None:
        if self.expected_rank is not None:
            _require_positive_int(self.expected_rank, "expected_rank")
        _require_optional_finite_float(self.expected_score, "expected_score")
        _require_optional_text(
            self.best_competitor_runtime_entry_id,
            "best_competitor_runtime_entry_id",
        )
        _require_optional_text(self.best_competitor_fact_id, "best_competitor_fact_id")
        _require_optional_finite_float(
            self.best_competitor_score,
            "best_competitor_score",
        )
        _require_optional_finite_float(self.score_margin, "score_margin")
        if not isinstance(self.classification, WorkbenchRagEvalRetrievalClassification):
            raise TypeError("classification must be retrieval classification")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalVerificationRoleMetrics:
    query_count: int
    top1_hits: int
    top3_hits: int
    top5_hits: int
    top1_rate: float
    top3_rate: float
    top5_rate: float
    mean_expected_rank: float
    mean_expected_score: float
    mean_score_margin: float
    miss_count: int
    confusion_count: int
    existing_alias_failure_count: int
    strong_pass_count: int
    weak_pass_count: int
    before_top1_hits: int = 0
    before_top3_hits: int = 0
    before_top5_hits: int = 0
    before_top1_rate: float = 0.0
    before_top3_rate: float = 0.0
    before_top5_rate: float = 0.0
    before_mean_expected_rank: float = 0.0
    before_mean_score_margin: float = 0.0
    top1_rate_delta: float = 0.0
    top3_rate_delta: float = 0.0
    top5_rate_delta: float = 0.0
    mean_expected_rank_delta: float = 0.0
    mean_score_margin_delta: float = 0.0
    promoted_top3_improvement_count: int = 0
    promoted_top3_regression_count: int = 0
    promoted_mean_margin_delta: float = 0.0
    holdout_top3_recall_before: float = 0.0
    holdout_top3_recall_after: float = 0.0
    holdout_top3_recall_delta: float = 0.0
    holdout_mean_margin_delta: float = 0.0
    baseline_top3_recall_before: float = 0.0
    baseline_top3_recall_after: float = 0.0
    baseline_top3_recall_delta: float = 0.0
    baseline_regression_count: int = 0
    neighbor_query_count: int = 0
    neighbor_top1_regression_count: int = 0
    neighbor_top3_regression_count: int = 0
    neighbor_mean_margin_delta: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "query_count",
            "top1_hits",
            "top3_hits",
            "top5_hits",
            "miss_count",
            "confusion_count",
            "existing_alias_failure_count",
            "strong_pass_count",
            "weak_pass_count",
            "before_top1_hits",
            "before_top3_hits",
            "before_top5_hits",
            "promoted_top3_improvement_count",
            "promoted_top3_regression_count",
            "baseline_regression_count",
            "neighbor_query_count",
            "neighbor_top1_regression_count",
            "neighbor_top3_regression_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        for field_name in (
            "top1_rate",
            "top3_rate",
            "top5_rate",
            "mean_expected_rank",
            "mean_expected_score",
            "mean_score_margin",
            "before_top1_rate",
            "before_top3_rate",
            "before_top5_rate",
            "before_mean_expected_rank",
            "before_mean_score_margin",
            "top1_rate_delta",
            "top3_rate_delta",
            "top5_rate_delta",
            "mean_expected_rank_delta",
            "mean_score_margin_delta",
            "promoted_mean_margin_delta",
            "holdout_top3_recall_before",
            "holdout_top3_recall_after",
            "holdout_top3_recall_delta",
            "holdout_mean_margin_delta",
            "baseline_top3_recall_before",
            "baseline_top3_recall_after",
            "baseline_top3_recall_delta",
            "neighbor_mean_margin_delta",
        ):
            _require_finite_float(getattr(self, field_name), field_name)

    def to_json_dict(self) -> JsonObject:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalVerificationMetrics:
    overall: WorkbenchRagEvalVerificationRoleMetrics
    promoted: WorkbenchRagEvalVerificationRoleMetrics
    holdout: WorkbenchRagEvalVerificationRoleMetrics
    baseline: WorkbenchRagEvalVerificationRoleMetrics
    neighbour: WorkbenchRagEvalVerificationRoleMetrics

    @classmethod
    def from_outcome_pairs(
        cls,
        pairs: tuple[WorkbenchRagEvalVerificationOutcomePair, ...],
    ) -> WorkbenchRagEvalVerificationMetrics:
        for pair in pairs:
            if not isinstance(pair, WorkbenchRagEvalVerificationOutcomePair):
                raise TypeError("pairs must contain verification outcome pairs")
        return cls(
            overall=_metrics_for_pairs(pairs),
            promoted=_metrics_for_pairs(
                _filter_pairs(pairs, WorkbenchRagEvalVerificationDatasetRole.PROMOTED)
            ),
            holdout=_metrics_for_pairs(
                _filter_pairs(pairs, WorkbenchRagEvalVerificationDatasetRole.HOLDOUT)
            ),
            baseline=_metrics_for_pairs(
                _filter_pairs(pairs, WorkbenchRagEvalVerificationDatasetRole.BASELINE)
            ),
            neighbour=_metrics_for_pairs(
                _filter_pairs(pairs, WorkbenchRagEvalVerificationDatasetRole.NEIGHBOUR)
            ),
        )

    def to_json_dict(self) -> JsonObject:
        return {
            "overall": self.overall.to_json_dict(),
            "promoted": self.promoted.to_json_dict(),
            "holdout": self.holdout.to_json_dict(),
            "baseline": self.baseline.to_json_dict(),
            "neighbour": self.neighbour.to_json_dict(),
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalVerificationPolicyDecision:
    decision: WorkbenchRagEvalVerificationDecision
    failure_reasons: tuple[WorkbenchRagEvalVerificationFailureReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkbenchRagEvalVerificationDecision):
            raise TypeError("decision must be WorkbenchRagEvalVerificationDecision")
        for reason in self.failure_reasons:
            if not isinstance(reason, WorkbenchRagEvalVerificationFailureReason):
                raise TypeError("failure_reasons must contain verification reasons")
        if (
            self.decision is WorkbenchRagEvalVerificationDecision.ACCEPTABLE
            and self.failure_reasons
        ):
            raise ValueError("acceptable decision cannot have failure reasons")
        if (
            self.decision is WorkbenchRagEvalVerificationDecision.REGRESSION
            and not self.failure_reasons
        ):
            raise ValueError("regression decision requires failure reasons")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalVerificationReadModel:
    verification_id: str
    revision_id: str
    project_id: str
    source_rag_eval_run_id: str
    runtime_entry_id: str
    status: WorkbenchRagEvalVerificationStatus
    policy_version: str
    decision: WorkbenchRagEvalVerificationDecision | None
    failure_reasons: tuple[WorkbenchRagEvalVerificationFailureReason, ...]
    metrics: JsonObject | None
    query_count: int
    outcome_count: int
    created_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    error_message: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "verification_id",
            "revision_id",
            "project_id",
            "source_rag_eval_run_id",
            "runtime_entry_id",
            "policy_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        if not isinstance(self.status, WorkbenchRagEvalVerificationStatus):
            raise TypeError("status must be verification status")
        if self.decision is not None and not isinstance(
            self.decision,
            WorkbenchRagEvalVerificationDecision,
        ):
            raise TypeError("decision must be verification decision or None")
        for reason in self.failure_reasons:
            if not isinstance(reason, WorkbenchRagEvalVerificationFailureReason):
                raise TypeError("failure_reasons must contain verification reasons")
        _require_non_negative_int(self.query_count, "query_count")
        _require_non_negative_int(self.outcome_count, "outcome_count")
        _require_datetime(self.created_at, "created_at")
        _require_optional_datetime(self.completed_at, "completed_at")
        _require_optional_datetime(self.failed_at, "failed_at")
        _require_optional_text(self.error_message, "error_message")

    def to_json_dict(self) -> JsonObject:
        return {
            "verification_id": self.verification_id,
            "revision_id": self.revision_id,
            "project_id": self.project_id,
            "source_rag_eval_run_id": self.source_rag_eval_run_id,
            "runtime_entry_id": self.runtime_entry_id,
            "status": self.status.value,
            "policy_version": self.policy_version,
            "decision": self.decision.value if self.decision is not None else None,
            "failure_reasons": [reason.value for reason in self.failure_reasons],
            "metrics": self.metrics,
            "query_count": self.query_count,
            "outcome_count": self.outcome_count,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at is not None
            else None,
            "failed_at": self.failed_at.isoformat()
            if self.failed_at is not None
            else None,
            "error_message": self.error_message,
        }


def _metrics_for_pairs(
    pairs: tuple[WorkbenchRagEvalVerificationOutcomePair, ...],
) -> WorkbenchRagEvalVerificationRoleMetrics:
    query_count = len(pairs)
    before_ranks = tuple(
        pair.before_expected_rank
        for pair in pairs
        if pair.before_expected_rank is not None
    )
    after_ranks = tuple(
        pair.after_expected_rank
        for pair in pairs
        if pair.after_expected_rank is not None
    )
    before_margins = tuple(
        pair.before_score_margin
        for pair in pairs
        if pair.before_score_margin is not None
    )
    after_scores = tuple(
        pair.after_expected_score
        for pair in pairs
        if pair.after_expected_score is not None
    )
    after_margins = tuple(
        pair.after_score_margin for pair in pairs if pair.after_score_margin is not None
    )
    before_top3_count = sum(1 for pair in pairs if pair.before_top3_hit)
    after_top3_count = sum(1 for pair in pairs if pair.after_top3_hit)
    before_top1_count = sum(1 for pair in pairs if pair.before_top1_hit)
    after_top1_count = sum(1 for pair in pairs if pair.after_top1_hit)
    before_top5_count = sum(1 for pair in pairs if pair.before_top5_hit)
    after_top5_count = sum(1 for pair in pairs if pair.after_top5_hit)
    before_mean_rank = _mean(before_ranks)
    after_mean_rank = _mean(after_ranks)
    before_mean_margin = _mean(before_margins)
    after_mean_margin = _mean(after_margins)
    margin_deltas = tuple(pair.margin_delta for pair in pairs)
    promoted_improvements = sum(
        1 for pair in pairs if not pair.before_top3_hit and pair.after_top3_hit
    )
    promoted_regressions = sum(
        1 for pair in pairs if pair.before_top3_hit and not pair.after_top3_hit
    )
    neighbor_top1_regressions = sum(
        1
        for pair in pairs
        if pair.dataset_role is WorkbenchRagEvalVerificationDatasetRole.NEIGHBOUR
        and pair.before_best_competitor_runtime_entry_id
        != pair.expected_runtime_entry_id
        and pair.after_best_competitor_runtime_entry_id
        == pair.expected_runtime_entry_id
        and pair.before_expected_rank == 1
    )
    neighbor_top3_regressions = sum(
        1
        for pair in pairs
        if pair.dataset_role is WorkbenchRagEvalVerificationDatasetRole.NEIGHBOUR
        and pair.before_best_competitor_runtime_entry_id
        != pair.expected_runtime_entry_id
        and pair.after_best_competitor_runtime_entry_id
        == pair.expected_runtime_entry_id
        and pair.before_top3_hit
    )
    baseline_regressions = sum(
        1
        for pair in pairs
        if pair.dataset_role is WorkbenchRagEvalVerificationDatasetRole.BASELINE
        and pair.before_top3_hit
        and not pair.after_top3_hit
    )
    return WorkbenchRagEvalVerificationRoleMetrics(
        query_count=query_count,
        top1_hits=after_top1_count,
        top3_hits=after_top3_count,
        top5_hits=after_top5_count,
        top1_rate=_rate(after_top1_count, query_count),
        top3_rate=_rate(after_top3_count, query_count),
        top5_rate=_rate(after_top5_count, query_count),
        mean_expected_rank=after_mean_rank,
        mean_expected_score=_mean(after_scores),
        mean_score_margin=after_mean_margin,
        miss_count=sum(
            1
            for pair in pairs
            if pair.after_classification is WorkbenchRagEvalRetrievalClassification.MISS
        ),
        confusion_count=sum(
            1
            for pair in pairs
            if pair.after_classification
            is WorkbenchRagEvalRetrievalClassification.CONFUSION
        ),
        existing_alias_failure_count=sum(
            1
            for pair in pairs
            if pair.after_classification
            is WorkbenchRagEvalRetrievalClassification.EXISTING_ALIAS_RETRIEVAL_FAILURE
        ),
        strong_pass_count=sum(
            1
            for pair in pairs
            if pair.after_classification
            is WorkbenchRagEvalRetrievalClassification.PASS_STRONG
        ),
        weak_pass_count=sum(
            1
            for pair in pairs
            if pair.after_classification
            is WorkbenchRagEvalRetrievalClassification.PASS_WEAK
        ),
        before_top1_hits=before_top1_count,
        before_top3_hits=before_top3_count,
        before_top5_hits=before_top5_count,
        before_top1_rate=_rate(before_top1_count, query_count),
        before_top3_rate=_rate(before_top3_count, query_count),
        before_top5_rate=_rate(before_top5_count, query_count),
        before_mean_expected_rank=before_mean_rank,
        before_mean_score_margin=before_mean_margin,
        top1_rate_delta=_rate(after_top1_count, query_count)
        - _rate(before_top1_count, query_count),
        top3_rate_delta=_rate(after_top3_count, query_count)
        - _rate(before_top3_count, query_count),
        top5_rate_delta=_rate(after_top5_count, query_count)
        - _rate(before_top5_count, query_count),
        mean_expected_rank_delta=after_mean_rank - before_mean_rank,
        mean_score_margin_delta=after_mean_margin - before_mean_margin,
        promoted_top3_improvement_count=promoted_improvements,
        promoted_top3_regression_count=promoted_regressions,
        promoted_mean_margin_delta=_mean(margin_deltas),
        holdout_top3_recall_before=_rate(before_top3_count, query_count),
        holdout_top3_recall_after=_rate(after_top3_count, query_count),
        holdout_top3_recall_delta=_rate(after_top3_count, query_count)
        - _rate(before_top3_count, query_count),
        holdout_mean_margin_delta=_mean(margin_deltas),
        baseline_top3_recall_before=_rate(before_top3_count, query_count),
        baseline_top3_recall_after=_rate(after_top3_count, query_count),
        baseline_top3_recall_delta=_rate(after_top3_count, query_count)
        - _rate(before_top3_count, query_count),
        baseline_regression_count=baseline_regressions,
        neighbor_query_count=sum(
            1
            for pair in pairs
            if pair.dataset_role is WorkbenchRagEvalVerificationDatasetRole.NEIGHBOUR
        ),
        neighbor_top1_regression_count=neighbor_top1_regressions,
        neighbor_top3_regression_count=neighbor_top3_regressions,
        neighbor_mean_margin_delta=_mean(margin_deltas),
    )


def _filter_pairs(
    pairs: tuple[WorkbenchRagEvalVerificationOutcomePair, ...],
    role: WorkbenchRagEvalVerificationDatasetRole,
) -> tuple[WorkbenchRagEvalVerificationOutcomePair, ...]:
    return tuple(pair for pair in pairs if pair.dataset_role is role)


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return count / total


def _mean(values: tuple[float | int, ...]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _zero_if_none(value: float | None) -> float:
    return 0.0 if value is None else float(value)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_text(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(f"{field_name} must be stripped text or None")


def _require_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware datetime")


def _require_optional_datetime(value: datetime | None, field_name: str) -> None:
    if value is None:
        return
    _require_datetime(value, field_name)


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_optional_finite_float(value: float | None, field_name: str) -> None:
    if value is None:
        return
    _require_finite_float(float(value), field_name)


def _require_finite_float(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be finite")
