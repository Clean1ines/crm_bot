from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_normalization_policy import (
    normalize_workbench_rag_eval_question,
)
from src.domain.project_plane.json_types import JsonObject


WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS = 384


class WorkbenchRagEvalEmbeddingRevisionStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    ACCEPTED = "accepted"
    REGRESSION_FAILED = "regression_failed"
    ROLLED_BACK = "rolled_back"


class WorkbenchRagEvalPromotionApplicationClaimStatus(StrEnum):
    PREPARING = "PREPARING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkbenchRagEvalPromotionApplicationClaimDecisionCode(StrEnum):
    ACQUIRED = "ACQUIRED"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    IN_PROGRESS = "IN_PROGRESS"
    RECOVERED_EXPIRED_LEASE = "RECOVERED_EXPIRED_LEASE"
    CONFLICTING_ACTIVE_GROUP = "CONFLICTING_ACTIVE_GROUP"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalEmbeddingRevisionAvailableActions:
    can_accept: bool
    can_rollback: bool

    def __post_init__(self) -> None:
        if not isinstance(self.can_accept, bool):
            raise TypeError("can_accept must be bool")
        if not isinstance(self.can_rollback, bool):
            raise TypeError("can_rollback must be bool")

    def to_json_dict(self) -> JsonObject:
        return {
            "can_accept": self.can_accept,
            "can_rollback": self.can_rollback,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationCandidate:
    promotion_id: str
    run_id: str
    question_id: str
    target_fact_id: str
    question: str
    status: WorkbenchRagEvalPromotionStatus

    def __post_init__(self) -> None:
        _require_text(self.promotion_id, "promotion_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.question_id, "question_id")
        _require_text(self.target_fact_id, "target_fact_id")
        _require_text(self.question, "question")
        if not isinstance(self.status, WorkbenchRagEvalPromotionStatus):
            raise TypeError("status must be WorkbenchRagEvalPromotionStatus")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationSnapshot:
    project_id: str
    runtime_entry_id: str
    fact_id: str
    runtime_status: str
    runtime_visibility: str
    claim: str
    possible_questions: tuple[str, ...]
    active_promoted_questions: tuple[str, ...]
    exclusion_scope: str | None
    embedding_text: str
    embedding: tuple[float, ...]
    embedding_model_id: str
    embedding_dimensions: int
    candidates: tuple[WorkbenchRagEvalPromotionApplicationCandidate, ...]
    runtime_hash: str
    active_revision_id: str | None

    def __post_init__(self) -> None:
        _require_text(self.project_id, "project_id")
        _require_text(self.runtime_entry_id, "runtime_entry_id")
        _require_text(self.fact_id, "fact_id")
        _require_text(self.runtime_status, "runtime_status")
        _require_text(self.runtime_visibility, "runtime_visibility")
        _require_text(self.claim, "claim")
        _require_unique_normalized_questions(
            self.possible_questions,
            "possible_questions",
        )
        _require_unique_normalized_questions(
            self.active_promoted_questions,
            "active_promoted_questions",
        )
        _require_optional_text(self.exclusion_scope, "exclusion_scope")
        _require_text(self.embedding_text, "embedding_text")
        _require_canonical_embedding_dimensions(self.embedding_dimensions)
        _require_vector(self.embedding, "embedding")
        _require_text(self.embedding_model_id, "embedding_model_id")
        if not isinstance(self.candidates, tuple) or not self.candidates:
            raise ValueError("candidates must be a non-empty tuple")
        for candidate in self.candidates:
            if not isinstance(candidate, WorkbenchRagEvalPromotionApplicationCandidate):
                raise TypeError(
                    "candidates must contain WorkbenchRagEvalPromotionApplicationCandidate"
                )
        _require_text(self.runtime_hash, "runtime_hash")
        _require_optional_text(self.active_revision_id, "active_revision_id")

    @property
    def source_rag_eval_run_id(self) -> str:
        run_ids = {candidate.run_id for candidate in self.candidates}
        if len(run_ids) != 1:
            raise ValueError(
                "promotion application group must contain exactly one run_id"
            )
        return next(iter(run_ids))


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalEmbeddingRevision:
    revision_id: str
    project_id: str
    runtime_entry_id: str
    source_rag_eval_run_id: str
    promotion_ids: tuple[str, ...]
    status: WorkbenchRagEvalEmbeddingRevisionStatus
    previous_embedding_text: str
    new_embedding_text: str
    previous_embedding: tuple[float, ...]
    new_embedding: tuple[float, ...]
    previous_promoted_questions: tuple[str, ...]
    new_promoted_questions: tuple[str, ...]
    embedding_model_id: str
    embedding_dimensions: int
    previous_runtime_hash: str
    new_runtime_hash: str
    created_at: datetime
    accepted_at: datetime | None
    regression_failed_at: datetime | None
    rolled_back_at: datetime | None

    def __post_init__(self) -> None:
        for field_name in (
            "revision_id",
            "project_id",
            "runtime_entry_id",
            "source_rag_eval_run_id",
            "previous_embedding_text",
            "new_embedding_text",
            "embedding_model_id",
            "previous_runtime_hash",
            "new_runtime_hash",
        ):
            _require_text(getattr(self, field_name), field_name)

        _require_unique_texts(self.promotion_ids, "promotion_ids")
        _require_canonical_embedding_dimensions(self.embedding_dimensions)
        _require_vector(self.previous_embedding, "previous_embedding")
        _require_vector(self.new_embedding, "new_embedding")
        _require_unique_normalized_questions(
            self.previous_promoted_questions,
            "previous_promoted_questions",
        )
        _require_unique_normalized_questions(
            self.new_promoted_questions,
            "new_promoted_questions",
        )
        if not isinstance(self.status, WorkbenchRagEvalEmbeddingRevisionStatus):
            raise TypeError("status must be WorkbenchRagEvalEmbeddingRevisionStatus")
        _require_datetime(self.created_at, "created_at")
        _require_optional_datetime(self.accepted_at, "accepted_at")
        _require_optional_datetime(
            self.regression_failed_at,
            "regression_failed_at",
        )
        _require_optional_datetime(self.rolled_back_at, "rolled_back_at")
        self._validate_status_timestamps()

    def _validate_status_timestamps(self) -> None:
        if self.status is WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION:
            if any(
                value is not None
                for value in (
                    self.accepted_at,
                    self.regression_failed_at,
                    self.rolled_back_at,
                )
            ):
                raise ValueError(
                    "PENDING_VERIFICATION revision cannot have terminal timestamps"
                )
            return

        if self.status is WorkbenchRagEvalEmbeddingRevisionStatus.ACCEPTED:
            if self.accepted_at is None:
                raise ValueError("ACCEPTED revision requires accepted_at")
            if self.regression_failed_at is not None or self.rolled_back_at is not None:
                raise ValueError(
                    "ACCEPTED revision cannot have regression/rollback timestamps"
                )
            return

        if self.status is WorkbenchRagEvalEmbeddingRevisionStatus.REGRESSION_FAILED:
            if self.regression_failed_at is None:
                raise ValueError(
                    "REGRESSION_FAILED revision requires regression_failed_at"
                )
            if self.accepted_at is not None or self.rolled_back_at is not None:
                raise ValueError(
                    "REGRESSION_FAILED revision cannot have accepted/rollback timestamps"
                )
            return

        if self.status is WorkbenchRagEvalEmbeddingRevisionStatus.ROLLED_BACK:
            if self.rolled_back_at is None:
                raise ValueError("ROLLED_BACK revision requires rolled_back_at")
            if self.accepted_at is not None:
                raise ValueError("ROLLED_BACK revision cannot have accepted_at")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalEmbeddingRevisionReadModel:
    revision_id: str
    project_id: str
    runtime_entry_id: str
    source_rag_eval_run_id: str
    promotion_ids: tuple[str, ...]
    status: WorkbenchRagEvalEmbeddingRevisionStatus
    previous_promoted_questions: tuple[str, ...]
    new_promoted_questions: tuple[str, ...]
    created_at: datetime
    accepted_at: datetime | None
    regression_failed_at: datetime | None
    rolled_back_at: datetime | None
    available_actions: WorkbenchRagEvalEmbeddingRevisionAvailableActions = (
        WorkbenchRagEvalEmbeddingRevisionAvailableActions(
            can_accept=False,
            can_rollback=False,
        )
    )

    def __post_init__(self) -> None:
        for field_name in (
            "revision_id",
            "project_id",
            "runtime_entry_id",
            "source_rag_eval_run_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_unique_texts(self.promotion_ids, "promotion_ids")
        _require_unique_normalized_questions(
            self.previous_promoted_questions,
            "previous_promoted_questions",
        )
        _require_unique_normalized_questions(
            self.new_promoted_questions,
            "new_promoted_questions",
        )
        if not isinstance(self.status, WorkbenchRagEvalEmbeddingRevisionStatus):
            raise TypeError("status must be WorkbenchRagEvalEmbeddingRevisionStatus")
        _require_datetime(self.created_at, "created_at")
        _require_optional_datetime(self.accepted_at, "accepted_at")
        _require_optional_datetime(
            self.regression_failed_at,
            "regression_failed_at",
        )
        _require_optional_datetime(self.rolled_back_at, "rolled_back_at")
        if not isinstance(
            self.available_actions,
            WorkbenchRagEvalEmbeddingRevisionAvailableActions,
        ):
            raise TypeError(
                "available_actions must be "
                "WorkbenchRagEvalEmbeddingRevisionAvailableActions"
            )

    def to_json_dict(self) -> JsonObject:
        return {
            "revision_id": self.revision_id,
            "project_id": self.project_id,
            "runtime_entry_id": self.runtime_entry_id,
            "source_rag_eval_run_id": self.source_rag_eval_run_id,
            "promotion_ids": list(self.promotion_ids),
            "status": self.status.value,
            "previous_promoted_questions": list(self.previous_promoted_questions),
            "new_promoted_questions": list(self.new_promoted_questions),
            "created_at": self.created_at.isoformat(),
            "accepted_at": (
                self.accepted_at.isoformat() if self.accepted_at is not None else None
            ),
            "regression_failed_at": (
                self.regression_failed_at.isoformat()
                if self.regression_failed_at is not None
                else None
            ),
            "rolled_back_at": (
                self.rolled_back_at.isoformat()
                if self.rolled_back_at is not None
                else None
            ),
            "available_actions": self.available_actions.to_json_dict(),
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationClaim:
    application_key: str
    project_id: str
    runtime_entry_id: str
    source_rag_eval_run_id: str
    promotion_ids: tuple[str, ...]
    previous_runtime_hash: str
    status: WorkbenchRagEvalPromotionApplicationClaimStatus
    lease_owner: str
    lease_expires_at: datetime
    revision_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    def __post_init__(self) -> None:
        for field_name in (
            "application_key",
            "project_id",
            "runtime_entry_id",
            "source_rag_eval_run_id",
            "previous_runtime_hash",
            "lease_owner",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_unique_texts(self.promotion_ids, "promotion_ids")
        if not isinstance(self.status, WorkbenchRagEvalPromotionApplicationClaimStatus):
            raise TypeError(
                "status must be WorkbenchRagEvalPromotionApplicationClaimStatus"
            )
        _require_datetime(self.lease_expires_at, "lease_expires_at")
        _require_optional_text(self.revision_id, "revision_id")
        _require_datetime(self.created_at, "created_at")
        _require_datetime(self.updated_at, "updated_at")
        _require_optional_datetime(self.completed_at, "completed_at")
        if self.status is WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING:
            if self.revision_id is not None or self.completed_at is not None:
                raise ValueError(
                    "PREPARING claim cannot have revision_id or completed_at"
                )
        elif self.status is WorkbenchRagEvalPromotionApplicationClaimStatus.COMPLETED:
            if self.revision_id is None or self.completed_at is None:
                raise ValueError(
                    "COMPLETED claim requires revision_id and completed_at"
                )
        elif self.revision_id is not None:
            raise ValueError("FAILED claim cannot have revision_id")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationClaimDecision:
    code: WorkbenchRagEvalPromotionApplicationClaimDecisionCode
    claim: WorkbenchRagEvalPromotionApplicationClaim
    revision: WorkbenchRagEvalEmbeddingRevisionReadModel | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.code,
            WorkbenchRagEvalPromotionApplicationClaimDecisionCode,
        ):
            raise TypeError(
                "code must be WorkbenchRagEvalPromotionApplicationClaimDecisionCode"
            )
        if not isinstance(self.claim, WorkbenchRagEvalPromotionApplicationClaim):
            raise TypeError("claim must be WorkbenchRagEvalPromotionApplicationClaim")
        if self.revision is not None and not isinstance(
            self.revision,
            WorkbenchRagEvalEmbeddingRevisionReadModel,
        ):
            raise TypeError(
                "revision must be WorkbenchRagEvalEmbeddingRevisionReadModel"
            )
        if (
            self.code
            is WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ALREADY_COMPLETED
            and self.revision is None
        ):
            raise ValueError("ALREADY_COMPLETED decision requires revision")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionRevisionResult:
    revision_id: str
    runtime_entry_id: str
    source_rag_eval_run_id: str
    status: WorkbenchRagEvalEmbeddingRevisionStatus
    promotion_ids: tuple[str, ...]
    idempotent: bool

    def __post_init__(self) -> None:
        _require_text(self.revision_id, "revision_id")
        _require_text(self.runtime_entry_id, "runtime_entry_id")
        _require_text(self.source_rag_eval_run_id, "source_rag_eval_run_id")
        _require_unique_texts(self.promotion_ids, "promotion_ids")
        if not isinstance(self.status, WorkbenchRagEvalEmbeddingRevisionStatus):
            raise TypeError("status must be WorkbenchRagEvalEmbeddingRevisionStatus")
        if not isinstance(self.idempotent, bool):
            raise TypeError("idempotent must be bool")

    def to_json_dict(self) -> JsonObject:
        return {
            "revision_id": self.revision_id,
            "runtime_entry_id": self.runtime_entry_id,
            "source_rag_eval_run_id": self.source_rag_eval_run_id,
            "status": self.status.value,
            "promotion_ids": list(self.promotion_ids),
            "idempotent": self.idempotent,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationError:
    code: str
    message: str
    promotion_ids: tuple[str, ...]
    runtime_entry_id: str | None

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_text(self.message, "message")
        _require_unique_texts(self.promotion_ids, "promotion_ids")
        _require_optional_text(self.runtime_entry_id, "runtime_entry_id")

    def to_json_dict(self) -> JsonObject:
        return {
            "code": self.code,
            "message": self.message,
            "promotion_ids": list(self.promotion_ids),
            "runtime_entry_id": self.runtime_entry_id,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationResult:
    requested_count: int
    applied_count: int
    skipped_count: int
    embedding_recalculation_count: int
    revisions: tuple[WorkbenchRagEvalPromotionRevisionResult, ...]
    errors: tuple[WorkbenchRagEvalPromotionApplicationError, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "requested_count",
            "applied_count",
            "skipped_count",
            "embedding_recalculation_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if not isinstance(self.revisions, tuple):
            raise TypeError("revisions must be tuple")
        if not isinstance(self.errors, tuple):
            raise TypeError("errors must be tuple")
        for revision in self.revisions:
            if not isinstance(revision, WorkbenchRagEvalPromotionRevisionResult):
                raise TypeError(
                    "revisions must contain WorkbenchRagEvalPromotionRevisionResult"
                )
        for error in self.errors:
            if not isinstance(error, WorkbenchRagEvalPromotionApplicationError):
                raise TypeError(
                    "errors must contain WorkbenchRagEvalPromotionApplicationError"
                )

    def to_json_dict(self) -> JsonObject:
        return {
            "requested_count": self.requested_count,
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "embedding_recalculation_count": self.embedding_recalculation_count,
            "revisions": [revision.to_json_dict() for revision in self.revisions],
            "errors": [error.to_json_dict() for error in self.errors],
        }


def stable_runtime_snapshot_hash(
    *,
    possible_questions: tuple[str, ...],
    embedding_text: str,
    embedding: tuple[float, ...],
    embedding_model_id: str,
    embedding_dimensions: int,
) -> str:
    _require_canonical_embedding_dimensions(embedding_dimensions)
    _require_vector(embedding, "embedding")
    payload = {
        "possible_questions": list(possible_questions),
        "embedding_text": embedding_text,
        "embedding": [float(value) for value in embedding],
        "embedding_model_id": embedding_model_id,
        "embedding_dimensions": WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    }
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def stable_promotion_application_key(
    *,
    project_id: str,
    runtime_entry_id: str,
    source_rag_eval_run_id: str,
    promotion_ids: tuple[str, ...],
    previous_runtime_hash: str,
) -> str:
    digest = _stable_application_identity_digest(
        project_id=project_id,
        runtime_entry_id=runtime_entry_id,
        source_rag_eval_run_id=source_rag_eval_run_id,
        promotion_ids=promotion_ids,
        previous_runtime_hash=previous_runtime_hash,
    )
    return f"rag-eval-promotion-application:{digest}"


def stable_embedding_revision_id(
    *,
    project_id: str,
    runtime_entry_id: str,
    source_rag_eval_run_id: str,
    promotion_ids: tuple[str, ...],
    previous_runtime_hash: str,
) -> str:
    digest = _stable_application_identity_digest(
        project_id=project_id,
        runtime_entry_id=runtime_entry_id,
        source_rag_eval_run_id=source_rag_eval_run_id,
        promotion_ids=promotion_ids,
        previous_runtime_hash=previous_runtime_hash,
    )
    return f"rag-eval-embedding-revision:{digest}"


def _stable_application_identity_digest(
    *,
    project_id: str,
    runtime_entry_id: str,
    source_rag_eval_run_id: str,
    promotion_ids: tuple[str, ...],
    previous_runtime_hash: str,
) -> str:
    for field_name, value in (
        ("project_id", project_id),
        ("runtime_entry_id", runtime_entry_id),
        ("source_rag_eval_run_id", source_rag_eval_run_id),
        ("previous_runtime_hash", previous_runtime_hash),
    ):
        _require_text(value, field_name)
    _require_unique_texts(promotion_ids, "promotion_ids")
    payload = "\x1f".join(
        (
            project_id,
            runtime_entry_id,
            source_rag_eval_run_id,
            *sorted(promotion_ids),
            previous_runtime_hash,
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value.strip()


def _require_optional_text(value: object, field_name: str) -> None:
    if value is None:
        return
    _require_text(value, field_name)


def _require_canonical_embedding_dimensions(value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
    ):
        raise ValueError(
            f"embedding_dimensions must equal {WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS}"
        )


def _require_non_negative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")


def _require_optional_datetime(value: object, field_name: str) -> None:
    if value is not None:
        _require_datetime(value, field_name)


def _require_vector(vector: object, field_name: str) -> None:
    if not isinstance(vector, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if len(vector) != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"{field_name} dimensions {len(vector)} do not match "
            f"{WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS}"
        )
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{field_name} must contain numeric values")
        if not math.isfinite(float(value)):
            raise ValueError(f"{field_name} must contain finite values")


def _require_unique_texts(values: object, field_name: str) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError(f"{field_name} must be a non-empty tuple")
    normalized: list[str] = []
    for value in values:
        normalized.append(_require_text(value, f"{field_name}[]"))
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must contain unique strings")


def _require_unique_normalized_questions(
    values: object,
    field_name: str,
) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple")
    normalized: list[str] = []
    for value in values:
        question = _require_text(value, f"{field_name}[]")
        canonical = normalize_workbench_rag_eval_question(question)
        if not canonical:
            raise ValueError(f"{field_name}[] normalizes to empty")
        normalized.append(canonical)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must contain unique normalized strings")
