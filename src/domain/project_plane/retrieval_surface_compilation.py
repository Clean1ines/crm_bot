from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
)
from src.domain.project_plane.model_usage_views import ModelUsageMeasurement

SurfaceKind = Literal[
    "umbrella","child","specific","standalone","definition","procedural","safety","handoff",
    "pricing","integration","channel","document_upload","curation","retrieval_quality",
    "commercial_terms","refund","payment","service_limits","other",
]
RelationType = Literal["umbrella_contains","specializes","sibling","duplicates","overlaps","contradicts","unrelated"]
QuestionKind = Literal["generated_variant","faq_question","test_question","user_like_question","expected_topic_hint","negative_test_question"]
SourceChildLabelKind = Literal["service_label","content_section","question_group","expected_topic","short_answer","other"]


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceSourceChild:
    title: str
    body: str
    raw_text: str
    label_kind: SourceChildLabelKind


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceSourceUnit:
    source_unit_key: str
    title: str
    body: str
    raw_text: str
    document_id: str | None = None
    source_chunk_indexes: tuple[int, ...] = ()
    children: tuple[RetrievalSurfaceSourceChild, ...] = ()
    section_path: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    preprocessing_mode: KnowledgePreprocessingMode = "faq"
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SurfaceQuestionReassignment:
    question: str
    target_surface_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceDraft:
    local_surface_key: str
    title: str
    canonical_question: str
    surface_kind: SurfaceKind
    answer_scope: str
    question_scope: str
    exclusion_scope: str
    source_excerpt: str = ""
    answer: str = ""
    short_answer: str = ""
    owned_questions: tuple[str, ...] = ()
    rejected_or_reassigned_questions: tuple[SurfaceQuestionReassignment, ...] = ()
    source_refs: tuple[str, ...] = ()
    parent_candidate_keys: tuple[str, ...] = ()
    child_candidate_keys: tuple[str, ...] = ()
    relation_hints: tuple[str, ...] = ()
    confidence: float = 0.7
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    source_chunk_indexes: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceRelation:
    parent_key: str
    child_key: str
    relation_type: RelationType
    reason: str
    confidence: float
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SurfaceQuestionOwnership:
    question: str
    owner_surface_key: str
    question_kind: QuestionKind
    confidence: float
    reason: str
    rejected_from_surface_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceGraph:
    source_unit_keys: tuple[str, ...]
    surfaces: tuple[RetrievalSurfaceDraft, ...]
    relations: tuple[RetrievalSurfaceRelation, ...]
    question_ownership: tuple[SurfaceQuestionOwnership, ...]
    metrics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceCompilationResult:
    mode: KnowledgePreprocessingMode
    prompt_version: str
    model: str
    graph: RetrievalSurfaceGraph
    projected_entries: tuple[KnowledgePreprocessingEntry, ...]
    metrics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceCompilationExecutionResult:
    result: RetrievalSurfaceCompilationResult
    usage: ModelUsageMeasurement | None = None
