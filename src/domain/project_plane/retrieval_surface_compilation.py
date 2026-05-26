from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias

from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode

SurfaceCompilerRunStatus: TypeAlias = Literal[
    "pending", "running", "completed", "failed", "cancelled"
]
SurfaceStatus: TypeAlias = Literal[
    "draft", "needs_review", "published", "rejected", "merged", "superseded"
]
SurfacePublicationStatus: TypeAlias = Literal[
    "unpublished", "publishing", "published", "publish_failed"
]
SurfaceKind: TypeAlias = Literal[
    "umbrella", "child", "specific", "standalone", "definition", "procedural",
    "safety", "handoff", "integration", "channel", "document_upload", "curation",
    "retrieval_quality", "service_limits", "other",
]
SurfaceRelationType: TypeAlias = Literal[
    "umbrella_contains", "specializes", "sibling", "duplicates", "overlaps", "contradicts", "unrelated"
]
SurfaceQuestionKind: TypeAlias = Literal[
    "faq_question", "test_question", "generated_variant", "user_like_question",
    "negative_test_question", "expected_topic_hint",
]
SurfaceSourceChildLabelKind: TypeAlias = Literal[
    "service_label", "content_section", "question_group", "expected_topic", "short_answer", "negative_test", "other"
]
SurfaceMergeDecisionType: TypeAlias = Literal["merge", "keep_separate"]


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceCompilerRun:
    id: str
    project_id: str
    document_id: str
    mode: KnowledgePreprocessingMode
    status: SurfaceCompilerRunStatus
    compiler_kind: str
    model: str
    prompt_version: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    metrics: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceCompilerStage:
    id: str
    run_id: str
    document_id: str
    stage_kind: str
    status: SurfaceCompilerRunStatus
    model: str
    prompt_version: str
    input_summary: str = ""
    output_summary: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    error_type: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metrics: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceSourceChild:
    title: str
    body: str
    raw_text: str
    label_kind: SurfaceSourceChildLabelKind
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceSourceUnit:
    id: str
    run_id: str
    document_id: str
    source_unit_key: str
    source_chunk_indexes: tuple[int, ...]
    title: str
    body: str
    children: tuple[RetrievalSurfaceSourceChild, ...]
    raw_text: str
    section_path: tuple[str, ...]
    source_refs: tuple[str, ...]
    preprocessing_mode: KnowledgePreprocessingMode
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceDraft:
    id: str
    run_id: str
    document_id: str
    local_surface_key: str
    title: str
    canonical_question: str
    surface_kind: SurfaceKind
    answer_scope: str
    question_scope: str
    exclusion_scope: str
    answer: str
    short_answer: str
    status: SurfaceStatus
    publication_status: SurfacePublicationStatus
    source_refs: tuple[str, ...]
    source_excerpt: str
    confidence: float
    warnings: tuple[str, ...] = ()
    metadata: JsonObject = field(default_factory=dict)
    source_chunk_indexes: tuple[int, ...] = ()
    linked_candidate_id: str | None = None
    linked_canonical_entry_id: str | None = None
    linked_runtime_entry_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceRelation:
    id: str
    run_id: str
    document_id: str
    parent_surface_key: str
    child_surface_key: str
    relation_type: SurfaceRelationType
    reason: str
    confidence: float
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SurfaceQuestionOwnership:
    id: str
    run_id: str
    document_id: str
    question: str
    owner_surface_key: str
    question_kind: SurfaceQuestionKind
    confidence: float
    reason: str
    rejected_from_surface_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SurfaceQuestionReassignment:
    id: str
    run_id: str
    document_id: str
    question: str
    from_surface_key: str
    to_surface_key: str
    reason: str
    confidence: float


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceMergeDecision:
    id: str
    run_id: str
    document_id: str
    survivor_surface_key: str
    merged_surface_keys: tuple[str, ...]
    keep_separate_surface_keys: tuple[str, ...]
    decision_type: SurfaceMergeDecisionType
    reason: str
    confidence: float


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceGraph:
    run_id: str
    document_id: str
    source_units: tuple[RetrievalSurfaceSourceUnit, ...]
    surfaces: tuple[RetrievalSurfaceDraft, ...]
    relations: tuple[RetrievalSurfaceRelation, ...]
    ownership: tuple[SurfaceQuestionOwnership, ...]
    reassignments: tuple[SurfaceQuestionReassignment, ...]
    merge_decisions: tuple[RetrievalSurfaceMergeDecision, ...]
    metrics: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceCompilationResult:
    mode: KnowledgePreprocessingMode
    prompt_version: str
    model: str
    graph: RetrievalSurfaceGraph
    metrics: JsonObject = field(default_factory=dict)
