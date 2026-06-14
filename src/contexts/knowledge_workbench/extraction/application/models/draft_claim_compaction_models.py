from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.domain.project_plane.json_types import JsonValue


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
    estimated_input_tokens: int
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
    estimated_input_tokens: int
    member_observation_refs: tuple[str, ...]

    @property
    def member_count(self) -> int:
        return len(self.member_observation_refs)


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
