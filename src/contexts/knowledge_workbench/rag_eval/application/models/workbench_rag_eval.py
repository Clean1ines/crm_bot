from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.domain.project_plane.json_types import JsonObject


class WorkbenchRagEvalRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkbenchRagEvalQuestionKind(StrEnum):
    PARAPHRASE = "paraphrase"
    SYNONYM = "synonym"
    NAIVE_USER_QUESTION = "naive_user_question"
    DOMAIN_SPECIFIC = "domain_specific"
    EXISTING_POSSIBLE_QUESTION = "existing_possible_question"


class WorkbenchRagEvalQuestionStatus(StrEnum):
    CREATED = "created"
    EVALUATED = "evaluated"
    FAILED = "failed"


class WorkbenchRagEvalQuestionSource(StrEnum):
    PUBLISHED_POSSIBLE_QUESTION = "published_possible_question"
    GENERATED = "generated"


class WorkbenchRagEvalPromotionStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


@dataclass(frozen=True, slots=True)
class GeneratedWorkbenchRagEvalQuestion:
    question: str
    question_kind: WorkbenchRagEvalQuestionKind
    source: WorkbenchRagEvalQuestionSource
    generation_model: str | None
    prompt_version: str | None
    generation_account_ref: str | None = None
    generation_slot_index: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.question, "question")
        _require_enum(self.question_kind, WorkbenchRagEvalQuestionKind, "question_kind")
        _require_enum(self.source, WorkbenchRagEvalQuestionSource, "source")
        _require_optional_text(self.generation_model, "generation_model")
        _require_optional_text(self.prompt_version, "prompt_version")
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

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.project_id, "project_id")
        _require_optional_text(self.publication_id, "publication_id")
        _require_optional_text(self.source_document_ref, "source_document_ref")
        _require_enum(self.status, WorkbenchRagEvalRunStatus, "status")
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
    generation_account_ref: str | None
    generation_slot_index: int | None
    status: WorkbenchRagEvalQuestionStatus
    created_at: datetime

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
        _require_optional_text(self.generation_account_ref, "generation_account_ref")
        _require_optional_non_negative_int(
            self.generation_slot_index, "generation_slot_index"
        )
        _require_enum(self.status, WorkbenchRagEvalQuestionStatus, "status")
        _require_datetime(self.created_at, "created_at")


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
    status: WorkbenchRagEvalQuestionStatus
    created_at: datetime
    results: tuple[WorkbenchRagEvalRetrievalResultDetails, ...]
    generation_account_ref: str | None = None
    generation_slot_index: int | None = None

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
        _require_enum(self.status, WorkbenchRagEvalQuestionStatus, "status")
        _require_datetime(self.created_at, "created_at")
        _require_optional_text(self.generation_account_ref, "generation_account_ref")
        _require_optional_non_negative_int(
            self.generation_slot_index, "generation_slot_index"
        )
        if not isinstance(self.results, tuple):
            raise TypeError("results must be tuple")

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
            "generation_account_ref": self.generation_account_ref,
            "generation_slot_index": self.generation_slot_index,
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

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.project_id, "project_id")
        _require_optional_text(self.publication_id, "publication_id")
        _require_optional_text(self.source_document_ref, "source_document_ref")
        _require_enum(self.status, WorkbenchRagEvalRunStatus, "status")
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

    def to_json_dict(self) -> JsonObject:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "publication_id": self.publication_id,
            "source_document_ref": self.source_document_ref,
            "status": self.status.value,
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
