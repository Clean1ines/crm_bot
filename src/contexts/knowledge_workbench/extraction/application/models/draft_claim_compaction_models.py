from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from src.domain.project_plane.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionGroupReadModel:
    group_ref: str
    workflow_run_id: str
    source_document_ref: str
    embedding_model_id: str
    group_algorithm: str
    group_threshold: float
    member_count: int
    artifact_tokens: int
    requires_split: bool
    created_at: datetime

    def __post_init__(self) -> None:
        for name, value in (
            ("group_ref", self.group_ref),
            ("workflow_run_id", self.workflow_run_id),
            ("source_document_ref", self.source_document_ref),
            ("embedding_model_id", self.embedding_model_id),
            ("group_algorithm", self.group_algorithm),
        ):
            _text(value, name)
        _score(self.group_threshold)
        _non_negative_int(self.member_count, "member_count")
        _non_negative_int(self.artifact_tokens, "artifact_tokens")
        _bool(self.requires_split, "requires_split")
        _datetime_value(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionBatchReadModel:
    batch_ref: str
    workflow_run_id: str
    group_ref: str
    prompt_variant: str
    model_id: str
    artifact_tokens: int
    batch_status: str
    member_count: int
    created_at: datetime

    def __post_init__(self) -> None:
        for name, value in (
            ("batch_ref", self.batch_ref),
            ("workflow_run_id", self.workflow_run_id),
            ("group_ref", self.group_ref),
            ("prompt_variant", self.prompt_variant),
            ("model_id", self.model_id),
            ("batch_status", self.batch_status),
        ):
            _text(value, name)
        _non_negative_int(self.artifact_tokens, "artifact_tokens")
        _non_negative_int(self.member_count, "member_count")
        _datetime_value(self.created_at, "created_at")

    @property
    def derived_work_item_id(self) -> str:
        return f"claim-compaction:{self.workflow_run_id}:{self.batch_ref}"


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionGroupMemberReadModel:
    group_ref: str
    observation_ref: str
    embedding_ref: str
    source_unit_ref: str
    member_rank: int
    member_kind: str
    created_at: datetime

    def __post_init__(self) -> None:
        for name, value in (
            ("group_ref", self.group_ref),
            ("observation_ref", self.observation_ref),
            ("embedding_ref", self.embedding_ref),
            ("source_unit_ref", self.source_unit_ref),
            ("member_kind", self.member_kind),
        ):
            _text(value, name)
        _non_negative_int(self.member_rank, "member_rank")
        _datetime_value(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class DraftClaimForCompaction:
    observation_ref: str
    embedding_ref: str
    workflow_run_id: str
    source_document_ref: str
    source_unit_ref: str
    claim: str
    possible_questions: tuple[str, ...]
    exclusion_scope: tuple[str, ...]
    granularity: str
    embedding_text: str
    embedding_model_id: str
    dimensions: int
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        for name, value in (
            ("observation_ref", self.observation_ref),
            ("embedding_ref", self.embedding_ref),
            ("workflow_run_id", self.workflow_run_id),
            ("source_document_ref", self.source_document_ref),
            ("source_unit_ref", self.source_unit_ref),
            ("claim", self.claim),
            ("granularity", self.granularity),
            ("embedding_text", self.embedding_text),
            ("embedding_model_id", self.embedding_model_id),
        ):
            _text(value, name)
        _text_tuple(self.possible_questions, "possible_questions", allow_empty=True)
        _text_tuple(self.exclusion_scope, "exclusion_scope", allow_empty=True)
        if self.dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if len(self.vector) != self.dimensions:
            raise ValueError("vector length must match dimensions")


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionEdgeCandidate:
    edge_ref: str
    workflow_run_id: str
    source_document_ref: str
    left_observation_ref: str
    right_observation_ref: str
    left_embedding_ref: str
    right_embedding_ref: str
    vector_score: float
    lexical_score: float
    question_overlap_score: float
    exclusion_scope_score: float
    granularity_score: float
    combined_score: float
    signals: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if self.left_observation_ref >= self.right_observation_ref:
            raise ValueError("left_observation_ref must be < right_observation_ref")
        for value in (
            self.vector_score,
            self.lexical_score,
            self.question_overlap_score,
            self.exclusion_scope_score,
            self.granularity_score,
            self.combined_score,
        ):
            _score(value)
        object.__setattr__(self, "signals", MappingProxyType(dict(self.signals)))


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionGroupCandidate:
    group_ref: str
    workflow_run_id: str
    source_document_ref: str
    embedding_model_id: str
    group_algorithm: str
    group_threshold: float
    member_observation_refs: tuple[str, ...]
    member_embedding_refs: tuple[str, ...]
    member_source_unit_refs: tuple[str, ...]
    artifact_tokens: int
    requires_split: bool

    @property
    def member_count(self) -> int:
        return len(self.member_observation_refs)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionBatchCandidate:
    batch_ref: str
    workflow_run_id: str
    group_ref: str
    prompt_variant: str
    model_id: str
    artifact_tokens: int
    member_observation_refs: tuple[str, ...]

    @property
    def member_count(self) -> int:
        return len(self.member_observation_refs)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionBatchForDispatch:
    batch_ref: str
    workflow_run_id: str
    group_ref: str
    prompt_variant: str
    model_id: str
    artifact_tokens: int
    member_observation_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.batch_ref, "batch_ref")
        _text(self.workflow_run_id, "workflow_run_id")
        _text(self.group_ref, "group_ref")
        _text(self.prompt_variant, "prompt_variant")
        _text(self.model_id, "model_id")
        if self.artifact_tokens < 0:
            raise ValueError("artifact_tokens must be >= 0")
        _text_tuple(
            self.member_observation_refs,
            "member_observation_refs",
            allow_empty=False,
        )

    @property
    def member_count(self) -> int:
        return len(self.member_observation_refs)


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")


def _bool(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be bool")


def _datetime_value(value: datetime, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _text_tuple(value: tuple[str, ...], name: str, *, allow_empty: bool) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be tuple")
    if not value and not allow_empty:
        raise ValueError(f"{name} must be non-empty")


def _score(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("score must be numeric")
    if value < 0 or value > 1:
        raise ValueError("score must be in [0, 1]")
