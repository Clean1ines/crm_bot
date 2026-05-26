from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from src.domain.project_plane.knowledge_compilation import SourceRef

RetrievalSurfaceKind: TypeAlias = Literal[
    "umbrella", "child", "specific", "standalone", "procedural", "safety", "pricing", "integration", "handoff", "definition", "other"
]

RetrievalSurfaceRelationType: TypeAlias = Literal[
    "umbrella_contains", "specializes", "sibling", "overlaps", "duplicates", "contradicts", "unrelated"
]

@dataclass(frozen=True, slots=True)
class RetrievalSurfaceCandidate:
    local_surface_key: str
    title: str
    canonical_question: str
    surface_kind: RetrievalSurfaceKind
    answer_scope: str
    question_scope: str
    exclusion_scope: str
    source_refs: tuple[SourceRef, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    parent_candidate_keys: tuple[str, ...] = field(default_factory=tuple)
    child_candidate_keys: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceRelation:
    parent_key: str
    child_key: str
    relation_type: RetrievalSurfaceRelationType
    confidence: float
    reason: str = ""
    source_refs: tuple[SourceRef, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SurfaceQuestionOwnership:
    question: str
    owner_surface_key: str
    question_kind: str = "user_like"
    confidence: float = 0.0
    reason: str = ""
    rejected_from_surface_keys: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceGraph:
    surfaces: tuple[RetrievalSurfaceCandidate, ...] = field(default_factory=tuple)
    relations: tuple[RetrievalSurfaceRelation, ...] = field(default_factory=tuple)
    question_ownership: tuple[SurfaceQuestionOwnership, ...] = field(default_factory=tuple)
