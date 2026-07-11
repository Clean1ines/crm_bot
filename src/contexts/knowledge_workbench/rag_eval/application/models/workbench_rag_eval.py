from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from src.domain.project_plane.json_types import JsonObject


class WorkbenchRagEvalRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_CAPACITY = "waiting_capacity"
    PROMOTION_REVIEW = "promotion_review"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class WorkbenchRagEvalCurrentPhase(StrEnum):
    SCOPE_RESOLUTION = "scope_resolution"
    QUESTION_GENERATION_SCHEDULING = "question_generation_scheduling"
    QUESTION_GENERATION = "question_generation"
    RETRIEVAL_EVALUATION = "retrieval_evaluation"
    ADJUDICATION_SCHEDULING = "adjudication_scheduling"
    ADJUDICATION = "adjudication"
    PROMOTION_REVIEW = "promotion_review"
    PROMOTION_APPLICATION = "promotion_application"
    POST_PROMOTION_VERIFICATION = "post_promotion_verification"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalRunProgress:
    selected_entries: int = 0
    scheduled_generation_items: int = 0
    waiting: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    generated_question_sets: int = 0
    adjudication_total: int = 0
    adjudication_waiting: int = 0
    adjudication_running: int = 0
    adjudication_completed: int = 0
    adjudication_failed: int = 0
    promotion_candidate_count: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "selected_entries",
            "scheduled_generation_items",
            "waiting",
            "running",
            "completed",
            "failed",
            "generated_question_sets",
            "adjudication_total",
            "adjudication_waiting",
            "adjudication_running",
            "adjudication_completed",
            "adjudication_failed",
            "promotion_candidate_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)

    def to_json_dict(self) -> JsonObject:
        return {
            "selected_entries": self.selected_entries,
            "scheduled_generation_items": self.scheduled_generation_items,
            "waiting": self.waiting,
            "running": self.running,
            "completed": self.completed,
            "failed": self.failed,
            "generated_question_sets": self.generated_question_sets,
            "adjudication_total": self.adjudication_total,
            "adjudication_waiting": self.adjudication_waiting,
            "adjudication_running": self.adjudication_running,
            "adjudication_completed": self.adjudication_completed,
            "adjudication_failed": self.adjudication_failed,
            "promotion_candidate_count": self.promotion_candidate_count,
        }


class WorkbenchRagEvalQuestionKind(StrEnum):
    DIRECT_PARAPHRASE = "direct_paraphrase"
    LEXICAL_VARIANT = "lexical_variant"
    NAIVE_USER = "naive_user"
    ENTITY_FIRST = "entity_first"
    ACTION_FIRST = "action_first"
    CONSTRAINT_FIRST = "constraint_first"
    DOMAIN_SPECIFIC = "domain_specific"
    EXISTING_POSSIBLE_QUESTION = "existing_possible_question"

    # Persisted V1 compatibility only. Strict V2 generation rejects these values.
    PARAPHRASE = "paraphrase"
    SYNONYM = "synonym"
    NAIVE_USER_QUESTION = "naive_user_question"


class WorkbenchRagEvalQuestionAmbiguityRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkbenchRagEvalQuestionStatus(StrEnum):
    CREATED = "created"
    EVALUATED = "evaluated"
    FAILED = "failed"


class WorkbenchRagEvalQuestionSource(StrEnum):
    PUBLISHED_POSSIBLE_QUESTION = "published_possible_question"
    GENERATED = "generated"


class WorkbenchRagEvalQuestionRole(StrEnum):
    BASELINE = "baseline"
    PROMOTION_POOL = "promotion_pool"
    HOLDOUT = "holdout"


class WorkbenchRagEvalRetrievalClassification(StrEnum):
    PASS_STRONG = "pass_strong"
    PASS_WEAK = "pass_weak"
    CONFUSION = "confusion"
    MISS = "miss"
    EXISTING_ALIAS_RETRIEVAL_FAILURE = "existing_alias_retrieval_failure"


class WorkbenchRagEvalPromotionStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


class WorkbenchRagEvalAdjudicationVerdict(StrEnum):
    VALID_TARGET_QUERY = "valid_target_query"
    AMBIGUOUS = "ambiguous"
    WRONG_EXPECTED_TARGET = "wrong_expected_target"
    UNSUPPORTED_BY_CLAIM = "unsupported_by_claim"
    DUPLICATE_QUERY = "duplicate_query"
    OVERLAPPING_PUBLISHED_ENTRIES = "overlapping_published_entries"


@dataclass(frozen=True, slots=True)
class GeneratedWorkbenchRagEvalQuestion:
    question: str
    question_kind: WorkbenchRagEvalQuestionKind
    source: WorkbenchRagEvalQuestionSource
    generation_model: str | None
    prompt_version: str | None
    contract_version: str
    promotion_eligible: bool
    ambiguity_risk: WorkbenchRagEvalQuestionAmbiguityRisk
    generation_rationale: str
    generation_account_ref: str | None = None
    generation_slot_index: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.question, "question")
        _require_enum(self.question_kind, WorkbenchRagEvalQuestionKind, "question_kind")
        _require_enum(self.source, WorkbenchRagEvalQuestionSource, "source")
        _require_optional_text(self.generation_model, "generation_model")
        _require_optional_text(self.prompt_version, "prompt_version")
        _require_text(self.contract_version, "contract_version")
        if not isinstance(self.promotion_eligible, bool):
            raise TypeError("promotion_eligible must be bool")
        _require_enum(
            self.ambiguity_risk,
            WorkbenchRagEvalQuestionAmbiguityRisk,
            "ambiguity_risk",
        )
        _require_text(self.generation_rationale, "generation_rationale")
        if (
            self.promotion_eligible
            and self.ambiguity_risk is not WorkbenchRagEvalQuestionAmbiguityRisk.LOW
        ):
            raise ValueError("promotion_eligible requires ambiguity_risk=low")
        _require_optional_text(self.generation_account_ref, "generation_account_ref")
        _require_optional_non_negative_int(
            self.generation_slot_index, "generation_slot_index"
        )


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalRun:
    run_id: str
    project_id: str
    publication_id: str | None
    source_document_ref: str | None
    status: WorkbenchRagEvalRunStatus
    question_generation_model: str | None
    question_generation_prompt_version: str
    total_entries: int
    total_questions: int
    completed_questions: int
    top1_hits: int
    top3_hits: int
    top5_hits: int
    misses: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    current_phase: WorkbenchRagEvalCurrentPhase = (
        WorkbenchRagEvalCurrentPhase.SCOPE_RESOLUTION
    )
    blocked_reason: str | None = None
    failed_reason: str | None = None
    updated_at: datetime | None = None
    progress: WorkbenchRagEvalRunProgress = field(
        default_factory=WorkbenchRagEvalRunProgress
    )
    capacity_next_due_at: datetime | None = None
    capacity_model_ref: str | None = None
    capacity_account_ref: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.project_id, "project_id")
        _require_optional_text(self.publication_id, "publication_id")
        _require_optional_text(self.source_document_ref, "source_document_ref")
        _require_enum(self.status, WorkbenchRagEvalRunStatus, "status")
        _require_enum(self.current_phase, WorkbenchRagEvalCurrentPhase, "current_phase")
        _require_optional_text(
            self.question_generation_model,
            "question_generation_model",
        )
        _require_text(
            self.question_generation_prompt_version,
            "question_generation_prompt_version",
        )
        for field_name in (
            "total_entries",
            "total_questions",
            "completed_questions",
            "top1_hits",
            "top3_hits",
            "top5_hits",
            "misses",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        _require_datetime(self.created_at, "created_at")
        _require_optional_datetime(self.started_at, "started_at")
        _require_optional_datetime(self.completed_at, "completed_at")
        _require_optional_text(self.error_message, "error_message")
        _require_optional_text(self.blocked_reason, "blocked_reason")
        _require_optional_text(self.failed_reason, "failed_reason")
        _require_optional_datetime(self.updated_at, "updated_at")
        if not isinstance(self.progress, WorkbenchRagEvalRunProgress):
            raise TypeError("progress must be WorkbenchRagEvalRunProgress")
        _require_optional_datetime(self.capacity_next_due_at, "capacity_next_due_at")
        _require_optional_text(self.capacity_model_ref, "capacity_model_ref")
        _require_optional_text(self.capacity_account_ref, "capacity_account_ref")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestion:
    question_id: str
    run_id: str
    project_id: str
    expected_runtime_entry_id: str
    expected_fact_id: str
    question: str
    question_kind: WorkbenchRagEvalQuestionKind
    source: WorkbenchRagEvalQuestionSource
    generation_model: str | None
    prompt_version: str | None
    contract_version: str | None
    promotion_eligible: bool
    ambiguity_risk: WorkbenchRagEvalQuestionAmbiguityRisk | None
    generation_rationale: str | None
    generation_account_ref: str | None
    generation_slot_index: int | None
    status: WorkbenchRagEvalQuestionStatus
    created_at: datetime
    evaluation_role: WorkbenchRagEvalQuestionRole

    def __post_init__(self) -> None:
        _require_text(self.question_id, "question_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.expected_runtime_entry_id, "expected_runtime_entry_id")
        _require_text(self.expected_fact_id, "expected_fact_id")
        _require_text(self.question, "question")
        _require_enum(self.question_kind, WorkbenchRagEvalQuestionKind, "question_kind")
        _require_enum(self.source, WorkbenchRagEvalQuestionSource, "source")
        _require_optional_text(self.generation_model, "generation_model")
        _require_optional_text(self.prompt_version, "prompt_version")
        _require_optional_text(self.contract_version, "contract_version")
        if not isinstance(self.promotion_eligible, bool):
            raise TypeError("promotion_eligible must be bool")
        if self.ambiguity_risk is not None:
            _require_enum(
                self.ambiguity_risk,
                WorkbenchRagEvalQuestionAmbiguityRisk,
                "ambiguity_risk",
            )
        _require_optional_text(self.generation_rationale, "generation_rationale")
        if (
            self.promotion_eligible
            and self.ambiguity_risk is not WorkbenchRagEvalQuestionAmbiguityRisk.LOW
        ):
            raise ValueError("promotion_eligible requires ambiguity_risk=low")
        _require_optional_text(self.generation_account_ref, "generation_account_ref")
        _require_optional_non_negative_int(
            self.generation_slot_index, "generation_slot_index"
        )
        _require_enum(self.status, WorkbenchRagEvalQuestionStatus, "status")
        _require_datetime(self.created_at, "created_at")
        _require_enum(
            self.evaluation_role, WorkbenchRagEvalQuestionRole, "evaluation_role"
        )
        if (
            self.evaluation_role is WorkbenchRagEvalQuestionRole.HOLDOUT
            and self.promotion_eligible
        ):
            raise ValueError("holdout question cannot be promotion eligible")
        _validate_question_source_role_contract(
            source=self.source,
            question_kind=self.question_kind,
            evaluation_role=self.evaluation_role,
            promotion_eligible=self.promotion_eligible,
            generation_model=self.generation_model,
            generation_account_ref=self.generation_account_ref,
            generation_slot_index=self.generation_slot_index,
        )


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalRetrievalResult:
    result_id: str
    run_id: str
    question_id: str
    project_id: str
    expected_runtime_entry_id: str
    matched_runtime_entry_id: str
    matched_fact_id: str
    rank: int
    score: float
    top1_hit: bool
    top3_hit: bool
    top5_hit: bool
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.result_id, "result_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.question_id, "question_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.expected_runtime_entry_id, "expected_runtime_entry_id")
        _require_text(self.matched_runtime_entry_id, "matched_runtime_entry_id")
        _require_text(self.matched_fact_id, "matched_fact_id")
        if self.rank < 1:
            raise ValueError("rank must be positive")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise TypeError("score must be numeric")
        if not isinstance(self.top1_hit, bool):
            raise TypeError("top1_hit must be bool")
        if not isinstance(self.top3_hit, bool):
            raise TypeError("top3_hit must be bool")
        if not isinstance(self.top5_hit, bool):
            raise TypeError("top5_hit must be bool")
        _require_datetime(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalRetrievalOutcome:
    outcome_id: str
    run_id: str
    question_id: str
    project_id: str
    evaluation_stage: str
    expected_runtime_entry_id: str
    expected_fact_id: str
    expected_rank: int | None
    expected_score: float | None
    best_competitor_runtime_entry_id: str | None
    best_competitor_fact_id: str | None
    best_competitor_score: float | None
    score_margin: float | None
    classification: WorkbenchRagEvalRetrievalClassification
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.outcome_id, "outcome_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.question_id, "question_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.evaluation_stage, "evaluation_stage")
        _require_text(
            self.expected_runtime_entry_id,
            "expected_runtime_entry_id",
        )
        _require_text(self.expected_fact_id, "expected_fact_id")

        if self.expected_rank is not None:
            if isinstance(self.expected_rank, bool) or not isinstance(
                self.expected_rank, int
            ):
                raise TypeError("expected_rank must be int or None")
            if self.expected_rank < 1:
                raise ValueError("expected_rank must be positive")

        for field_name in (
            "expected_score",
            "best_competitor_score",
            "score_margin",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise TypeError(f"{field_name} must be numeric or None")

        _require_optional_text(
            self.best_competitor_runtime_entry_id,
            "best_competitor_runtime_entry_id",
        )
        _require_optional_text(
            self.best_competitor_fact_id,
            "best_competitor_fact_id",
        )
        _require_enum(
            self.classification,
            WorkbenchRagEvalRetrievalClassification,
            "classification",
        )
        _require_datetime(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudication:
    adjudication_id: str
    run_id: str
    project_id: str
    question_id: str
    outcome_id: str
    expected_runtime_entry_id: str
    expected_fact_id: str
    verdict: WorkbenchRagEvalAdjudicationVerdict
    promotion_recommended: bool
    reason: str
    contract_version: str
    model_ref: str
    account_ref: str
    slot_index: int
    attempt_id: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "adjudication_id",
            "run_id",
            "project_id",
            "question_id",
            "outcome_id",
            "expected_runtime_entry_id",
            "expected_fact_id",
            "reason",
            "contract_version",
            "model_ref",
            "account_ref",
            "attempt_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_enum(self.verdict, WorkbenchRagEvalAdjudicationVerdict, "verdict")
        if not isinstance(self.promotion_recommended, bool):
            raise TypeError("promotion_recommended must be bool")
        if (
            self.promotion_recommended
            and self.verdict
            is not WorkbenchRagEvalAdjudicationVerdict.VALID_TARGET_QUERY
        ):
            raise ValueError("promotion recommendation requires valid target query")
        _require_non_negative_int(self.slot_index, "slot_index")
        _require_datetime(self.created_at, "created_at")
        _require_datetime(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotedQuestion:
    promotion_id: str
    run_id: str
    question_id: str
    project_id: str
    target_runtime_entry_id: str
    target_fact_id: str
    question: str
    status: WorkbenchRagEvalPromotionStatus
    created_at: datetime
    applied_at: datetime | None
    outcome_id: str | None = None
    adjudication_id: str | None = None
    reason: str | None = None
    expected_rank: int | None = None
    expected_score: float | None = None
    competitor_runtime_entry_id: str | None = None
    competitor_fact_id: str | None = None
    competitor_score: float | None = None
    score_margin: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.promotion_id, "promotion_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.question_id, "question_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.target_runtime_entry_id, "target_runtime_entry_id")
        _require_text(self.target_fact_id, "target_fact_id")
        _require_text(self.question, "question")
        _require_enum(self.status, WorkbenchRagEvalPromotionStatus, "status")
        _require_datetime(self.created_at, "created_at")
        _require_optional_datetime(self.applied_at, "applied_at")
        _require_optional_text(self.outcome_id, "outcome_id")
        _require_optional_text(self.adjudication_id, "adjudication_id")
        _require_optional_text(self.reason, "reason")
        if self.expected_rank is not None:
            _require_non_negative_int(self.expected_rank, "expected_rank")
            if self.expected_rank == 0:
                raise ValueError("expected_rank must be positive when provided")
        for field_name in (
            "expected_score",
            "competitor_score",
            "score_margin",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise TypeError(f"{field_name} must be numeric or None")
        _require_optional_text(
            self.competitor_runtime_entry_id,
            "competitor_runtime_entry_id",
        )
        _require_optional_text(self.competitor_fact_id, "competitor_fact_id")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalRetrievalResultDetails:
    result_id: str
    matched_runtime_entry_id: str
    matched_fact_id: str
    rank: int
    score: float
    top1_hit: bool
    top3_hit: bool
    top5_hit: bool
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.result_id, "result_id")
        _require_text(self.matched_runtime_entry_id, "matched_runtime_entry_id")
        _require_text(self.matched_fact_id, "matched_fact_id")
        if self.rank < 1:
            raise ValueError("rank must be positive")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise TypeError("score must be numeric")
        if not isinstance(self.top1_hit, bool):
            raise TypeError("top1_hit must be bool")
        if not isinstance(self.top3_hit, bool):
            raise TypeError("top3_hit must be bool")
        if not isinstance(self.top5_hit, bool):
            raise TypeError("top5_hit must be bool")
        _require_datetime(self.created_at, "created_at")

    def to_json_dict(self) -> JsonObject:
        return {
            "result_id": self.result_id,
            "matched_runtime_entry_id": self.matched_runtime_entry_id,
            "matched_fact_id": self.matched_fact_id,
            "rank": self.rank,
            "score": self.score,
            "top1_hit": self.top1_hit,
            "top3_hit": self.top3_hit,
            "top5_hit": self.top5_hit,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionDetails:
    question_id: str
    run_id: str
    project_id: str
    expected_runtime_entry_id: str
    expected_fact_id: str
    question: str
    question_kind: WorkbenchRagEvalQuestionKind
    source: WorkbenchRagEvalQuestionSource
    generation_model: str | None
    prompt_version: str | None
    contract_version: str | None
    promotion_eligible: bool
    ambiguity_risk: WorkbenchRagEvalQuestionAmbiguityRisk | None
    generation_rationale: str | None
    generation_account_ref: str | None
    generation_slot_index: int | None
    evaluation_role: WorkbenchRagEvalQuestionRole
    status: WorkbenchRagEvalQuestionStatus
    created_at: datetime
    results: tuple[WorkbenchRagEvalRetrievalResultDetails, ...]

    def __post_init__(self) -> None:
        _require_text(self.question_id, "question_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.expected_runtime_entry_id, "expected_runtime_entry_id")
        _require_text(self.expected_fact_id, "expected_fact_id")
        _require_text(self.question, "question")
        _require_enum(self.question_kind, WorkbenchRagEvalQuestionKind, "question_kind")
        _require_enum(self.source, WorkbenchRagEvalQuestionSource, "source")
        _require_optional_text(self.generation_model, "generation_model")
        _require_optional_text(self.prompt_version, "prompt_version")
        _require_optional_text(self.contract_version, "contract_version")
        if not isinstance(self.promotion_eligible, bool):
            raise TypeError("promotion_eligible must be bool")
        if self.ambiguity_risk is not None:
            _require_enum(
                self.ambiguity_risk,
                WorkbenchRagEvalQuestionAmbiguityRisk,
                "ambiguity_risk",
            )
        _require_optional_text(self.generation_rationale, "generation_rationale")
        if (
            self.promotion_eligible
            and self.ambiguity_risk is not WorkbenchRagEvalQuestionAmbiguityRisk.LOW
        ):
            raise ValueError("promotion_eligible requires ambiguity_risk=low")
        _require_enum(self.status, WorkbenchRagEvalQuestionStatus, "status")
        _require_datetime(self.created_at, "created_at")
        _require_optional_text(self.generation_account_ref, "generation_account_ref")
        _require_optional_non_negative_int(
            self.generation_slot_index, "generation_slot_index"
        )
        if not isinstance(self.results, tuple):
            raise TypeError("results must be tuple")
        _require_enum(
            self.evaluation_role, WorkbenchRagEvalQuestionRole, "evaluation_role"
        )
        _validate_question_source_role_contract(
            source=self.source,
            question_kind=self.question_kind,
            evaluation_role=self.evaluation_role,
            promotion_eligible=self.promotion_eligible,
            generation_model=self.generation_model,
            generation_account_ref=self.generation_account_ref,
            generation_slot_index=self.generation_slot_index,
        )

    def to_json_dict(self) -> JsonObject:
        return {
            "question_id": self.question_id,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "expected_runtime_entry_id": self.expected_runtime_entry_id,
            "expected_fact_id": self.expected_fact_id,
            "question": self.question,
            "question_kind": self.question_kind.value,
            "source": self.source.value,
            "generation_model": self.generation_model,
            "prompt_version": self.prompt_version,
            "contract_version": self.contract_version,
            "promotion_eligible": self.promotion_eligible,
            "ambiguity_risk": (
                self.ambiguity_risk.value if self.ambiguity_risk is not None else None
            ),
            "generation_rationale": self.generation_rationale,
            "generation_account_ref": self.generation_account_ref,
            "generation_slot_index": self.generation_slot_index,
            "evaluation_role": self.evaluation_role.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "results": [result.to_json_dict() for result in self.results],
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionCandidateDetails:
    promotion_id: str
    run_id: str
    question_id: str
    project_id: str
    target_runtime_entry_id: str
    target_fact_id: str
    question: str
    status: WorkbenchRagEvalPromotionStatus
    created_at: datetime
    applied_at: datetime | None

    def __post_init__(self) -> None:
        _require_text(self.promotion_id, "promotion_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.question_id, "question_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.target_runtime_entry_id, "target_runtime_entry_id")
        _require_text(self.target_fact_id, "target_fact_id")
        _require_text(self.question, "question")
        _require_enum(self.status, WorkbenchRagEvalPromotionStatus, "status")
        _require_datetime(self.created_at, "created_at")
        _require_optional_datetime(self.applied_at, "applied_at")

    def to_json_dict(self) -> JsonObject:
        return {
            "promotion_id": self.promotion_id,
            "run_id": self.run_id,
            "question_id": self.question_id,
            "project_id": self.project_id,
            "target_runtime_entry_id": self.target_runtime_entry_id,
            "target_fact_id": self.target_fact_id,
            "question": self.question,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat()
            if self.applied_at is not None
            else None,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationTarget:
    promotion_id: str
    run_id: str
    question_id: str
    project_id: str
    target_runtime_entry_id: str
    target_fact_id: str
    question: str
    status: WorkbenchRagEvalPromotionStatus
    claim: str
    runtime_possible_questions: tuple[str, ...]
    fact_possible_questions: tuple[str, ...]
    exclusion_scope: str | None
    existing_embedding_text: str

    def __post_init__(self) -> None:
        _require_text(self.promotion_id, "promotion_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.question_id, "question_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.target_runtime_entry_id, "target_runtime_entry_id")
        _require_text(self.target_fact_id, "target_fact_id")
        _require_text(self.question, "question")
        _require_enum(self.status, WorkbenchRagEvalPromotionStatus, "status")
        _require_text(self.claim, "claim")
        if not isinstance(self.runtime_possible_questions, tuple):
            raise TypeError("runtime_possible_questions must be tuple")
        if not isinstance(self.fact_possible_questions, tuple):
            raise TypeError("fact_possible_questions must be tuple")
        _require_optional_text(self.exclusion_scope, "exclusion_scope")
        _require_text(self.existing_embedding_text, "existing_embedding_text")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplyResult:
    promotion_id: str
    run_id: str
    question_id: str
    project_id: str
    target_runtime_entry_id: str
    target_fact_id: str
    question: str
    status: WorkbenchRagEvalPromotionStatus
    possible_question_count: int
    embedding_model_id: str
    embedding_count: int
    applied_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.promotion_id, "promotion_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.question_id, "question_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.target_runtime_entry_id, "target_runtime_entry_id")
        _require_text(self.target_fact_id, "target_fact_id")
        _require_text(self.question, "question")
        _require_enum(self.status, WorkbenchRagEvalPromotionStatus, "status")
        _require_non_negative_int(
            self.possible_question_count, "possible_question_count"
        )
        _require_text(self.embedding_model_id, "embedding_model_id")
        _require_non_negative_int(self.embedding_count, "embedding_count")
        _require_datetime(self.applied_at, "applied_at")

    def to_json_dict(self) -> JsonObject:
        return {
            "promotion_id": self.promotion_id,
            "run_id": self.run_id,
            "question_id": self.question_id,
            "project_id": self.project_id,
            "target_runtime_entry_id": self.target_runtime_entry_id,
            "target_fact_id": self.target_fact_id,
            "question": self.question,
            "status": self.status.value,
            "possible_question_count": self.possible_question_count,
            "embedding_model_id": self.embedding_model_id,
            "embedding_count": self.embedding_count,
            "applied_at": self.applied_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionBatchApplyResult:
    requested_count: int
    applied_count: int
    skipped_count: int
    embedding_recalculation_count: int
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_negative_int(self.requested_count, "requested_count")
        _require_non_negative_int(self.applied_count, "applied_count")
        _require_non_negative_int(self.skipped_count, "skipped_count")
        _require_non_negative_int(
            self.embedding_recalculation_count,
            "embedding_recalculation_count",
        )
        if not isinstance(self.errors, tuple):
            raise TypeError("errors must be tuple")
        for error in self.errors:
            _require_text(error, "errors[]")

    def to_json_dict(self) -> JsonObject:
        return {
            "requested_count": self.requested_count,
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "embedding_recalculation_count": self.embedding_recalculation_count,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalSummary:
    run_id: str
    project_id: str
    publication_id: str | None
    source_document_ref: str | None
    status: WorkbenchRagEvalRunStatus
    total_entries: int
    total_questions: int
    completed_questions: int
    top1_hits: int
    top3_hits: int
    top5_hits: int
    misses: int
    promotion_candidate_count: int
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None
    current_phase: WorkbenchRagEvalCurrentPhase = (
        WorkbenchRagEvalCurrentPhase.SCOPE_RESOLUTION
    )
    blocked_reason: str | None = None
    failed_reason: str | None = None
    updated_at: datetime | None = None
    progress: WorkbenchRagEvalRunProgress = field(
        default_factory=WorkbenchRagEvalRunProgress
    )
    capacity_next_due_at: datetime | None = None
    capacity_model_ref: str | None = None
    capacity_account_ref: str | None = None
    retrieval_total_questions: int = 0
    retrieval_evaluated_questions: int = 0
    retrieval_pass_strong: int = 0
    retrieval_pass_weak: int = 0
    retrieval_confusions: int = 0
    retrieval_misses: int = 0
    retrieval_existing_alias_failures: int = 0

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.project_id, "project_id")
        _require_optional_text(self.publication_id, "publication_id")
        _require_optional_text(self.source_document_ref, "source_document_ref")
        _require_enum(self.status, WorkbenchRagEvalRunStatus, "status")
        _require_enum(self.current_phase, WorkbenchRagEvalCurrentPhase, "current_phase")
        for field_name in (
            "total_entries",
            "total_questions",
            "completed_questions",
            "top1_hits",
            "top3_hits",
            "top5_hits",
            "misses",
            "promotion_candidate_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        _require_datetime(self.created_at, "created_at")
        _require_optional_datetime(self.completed_at, "completed_at")
        _require_optional_text(self.error_message, "error_message")
        _require_optional_text(self.blocked_reason, "blocked_reason")
        _require_optional_text(self.failed_reason, "failed_reason")
        _require_optional_datetime(self.updated_at, "updated_at")
        if not isinstance(self.progress, WorkbenchRagEvalRunProgress):
            raise TypeError("progress must be WorkbenchRagEvalRunProgress")
        for field_name in (
            "retrieval_total_questions",
            "retrieval_evaluated_questions",
            "retrieval_pass_strong",
            "retrieval_pass_weak",
            "retrieval_confusions",
            "retrieval_misses",
            "retrieval_existing_alias_failures",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        _require_optional_datetime(self.capacity_next_due_at, "capacity_next_due_at")
        _require_optional_text(self.capacity_model_ref, "capacity_model_ref")
        _require_optional_text(self.capacity_account_ref, "capacity_account_ref")

    def to_json_dict(self) -> JsonObject:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "publication_id": self.publication_id,
            "source_document_ref": self.source_document_ref,
            "status": self.status.value,
            "current_phase": self.current_phase.value,
            "scope": {
                "publication_id": self.publication_id,
                "source_document_ref": self.source_document_ref,
            },
            "progress": self.progress.to_json_dict(),
            "capacity_wait": (
                {
                    "next_due_at": self.capacity_next_due_at.isoformat(),
                    "model_ref": self.capacity_model_ref,
                    "account_ref": self.capacity_account_ref,
                }
                if self.capacity_next_due_at is not None
                else None
            ),
            "total_entries": self.total_entries,
            "total_questions": self.total_questions,
            "completed_questions": self.completed_questions,
            "top1_hits": self.top1_hits,
            "top3_hits": self.top3_hits,
            "top5_hits": self.top5_hits,
            "misses": self.misses,
            "promotion_candidate_count": self.promotion_candidate_count,
            "created_at": self.created_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at is not None else None
            ),
            "error_message": self.error_message,
            "blocked_reason": self.blocked_reason,
            "failed_reason": self.failed_reason,
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at is not None else None
            ),
            "retrieval_progress": {
                "total": self.retrieval_total_questions,
                "completed": self.retrieval_evaluated_questions,
                "classification_counts": {
                    "pass_strong": self.retrieval_pass_strong,
                    "pass_weak": self.retrieval_pass_weak,
                    "confusion": self.retrieval_confusions,
                    "miss": self.retrieval_misses,
                    "existing_alias_retrieval_failure": self.retrieval_existing_alias_failures,
                },
            },
        }


def triple_tuple(
    value: tuple[Mapping[str, object], ...],
) -> tuple[Mapping[str, object], ...]:
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError("triples must contain mappings")
    return value


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_text(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str or None")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative int")


def _require_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")


def _require_optional_datetime(value: datetime | None, field_name: str) -> None:
    if value is None:
        return
    _require_datetime(value, field_name)


def _require_enum(value: object, enum_type: type[StrEnum], field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{field_name} must be {enum_type.__name__}")


def _require_optional_non_negative_int(value: int | None, field_name: str) -> None:
    if value is None:
        return
    _require_non_negative_int(value, field_name)


def _validate_question_source_role_contract(
    *,
    source: WorkbenchRagEvalQuestionSource,
    question_kind: WorkbenchRagEvalQuestionKind,
    evaluation_role: WorkbenchRagEvalQuestionRole,
    promotion_eligible: bool,
    generation_model: str | None,
    generation_account_ref: str | None,
    generation_slot_index: int | None,
) -> None:
    if source is WorkbenchRagEvalQuestionSource.PUBLISHED_POSSIBLE_QUESTION:
        if question_kind is not WorkbenchRagEvalQuestionKind.EXISTING_POSSIBLE_QUESTION:
            raise ValueError("published possible question requires existing kind")
        if evaluation_role is not WorkbenchRagEvalQuestionRole.BASELINE:
            raise ValueError("published possible question requires baseline role")
        if promotion_eligible:
            raise ValueError("published possible question cannot be promotion eligible")
        if generation_model is not None:
            raise ValueError("published possible question cannot have generation model")
        if generation_account_ref is not None:
            raise ValueError(
                "published possible question cannot have generation account ref"
            )
        if generation_slot_index is not None:
            raise ValueError(
                "published possible question cannot have generation slot index"
            )
        return

    if source is WorkbenchRagEvalQuestionSource.GENERATED:
        if evaluation_role is WorkbenchRagEvalQuestionRole.BASELINE:
            raise ValueError("generated question cannot have baseline role")
        if evaluation_role not in {
            WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
            WorkbenchRagEvalQuestionRole.HOLDOUT,
        }:
            raise ValueError("generated question requires promotion_pool or holdout")
        if (
            evaluation_role is WorkbenchRagEvalQuestionRole.HOLDOUT
            and promotion_eligible
        ):
            raise ValueError("holdout question cannot be promotion eligible")
