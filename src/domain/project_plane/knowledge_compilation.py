from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping


Metadata = Mapping[str, object]


class KnowledgeEntryKind(StrEnum):
    ANSWER = "answer"
    FAQ_ANSWER = "faq_answer"
    CONTACT_INFO = "contact_info"
    WORKING_HOURS = "working_hours"
    CATALOG_ANSWER = "catalog_answer"
    PRICE_ANSWER = "price_answer"
    PRICING_POLICY = "pricing_policy"
    REFUND_POLICY = "refund_policy"
    DELIVERY_POLICY = "delivery_policy"
    POLICY_CLAUSE = "policy_clause"
    PROCEDURE = "procedure"
    WARNING = "warning"
    REQUIREMENT = "requirement"
    TROUBLESHOOTING_STEP = "troubleshooting_step"
    FALLBACK_CHUNK = "fallback_chunk"
    CUSTOM = "custom"


class KnowledgeEntryStatus(StrEnum):
    DRAFT = "draft"
    GROUNDED = "grounded"
    ENRICHED = "enriched"
    EMBEDDED = "embedded"
    PUBLISHED = "published"
    NEEDS_REVIEW = "needs_review"
    HIDDEN = "hidden"
    ARCHIVED = "archived"
    REJECTED = "rejected"
    MERGED = "merged"


class KnowledgeEntryVisibility(StrEnum):
    RUNTIME = "runtime"
    OWNER_ONLY = "owner_only"
    INTERNAL = "internal"
    HIDDEN = "hidden"


class CompilerRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CompilerBatchStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class AnswerCandidateStatus(StrEnum):
    EXTRACTED = "extracted"
    GROUNDED_CHECKED = "grounded_checked"
    CLUSTERED = "clustered"
    MERGED = "merged"
    REJECTED = "rejected"


class CandidateClusterStatus(StrEnum):
    CREATED = "created"
    MERGE_READY = "merge_ready"
    CANONICAL_ENTRY_CREATED = "canonical_entry_created"
    NEEDS_REVIEW = "needs_review"


class EvalCaseStatus(StrEnum):
    GENERATED = "generated"
    ACTIVE = "active"
    REGRESSION = "regression"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class SourceDocument:
    id: str
    project_id: str
    file_name: str
    file_size: int | None = None
    content_type: str | None = None
    uploaded_by: str | None = None
    status: str = "uploaded"
    processing_stage: str = "uploaded"
    preprocessing_mode: str = "faq"
    compiler_version: str = ""
    preprocessing_metrics: Metadata = field(default_factory=dict)
    error: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompilationMetrics:
    source_chunk_count: int = 0
    answer_candidate_count: int = 0
    grounded_candidate_count: int = 0
    rejected_candidate_count: int = 0
    candidate_cluster_count: int = 0
    canonical_entry_count: int = 0
    enriched_entry_count: int = 0
    embedded_entry_count: int = 0
    published_entry_count: int = 0
    fallback_row_count: int = 0
    dropped_forbidden_count: int = 0
    entries_without_source_refs_count: int = 0


@dataclass(frozen=True, slots=True)
class CompilerRun:
    id: str
    document_id: str
    project_id: str
    mode: str
    compiler_version: str
    prompt_version: str = ""
    model: str = ""
    status: CompilerRunStatus = CompilerRunStatus.CREATED
    metrics: CompilationMetrics = field(default_factory=CompilationMetrics)
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_by: str | None = None


@dataclass(frozen=True, slots=True)
class CompilerBatch:
    id: str
    document_id: str
    project_id: str
    compiler_run_id: str
    batch_index: int
    batch_count: int
    source_chunk_ids: tuple[str, ...] = ()
    source_chunk_indexes: tuple[int, ...] = ()
    status: CompilerBatchStatus = CompilerBatchStatus.PENDING
    attempt_count: int = 0
    model: str = ""
    prompt_version: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    error_type: str = ""
    error_message: str = ""
    metadata: Metadata = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.batch_index < 1:
            raise ValueError("CompilerBatch.batch_index must be positive")
        if self.batch_count < 1:
            raise ValueError("CompilerBatch.batch_count must be positive")
        if self.batch_index > self.batch_count:
            raise ValueError("CompilerBatch.batch_index must be <= batch_count")
        if self.attempt_count < 0:
            raise ValueError("CompilerBatch.attempt_count must be non-negative")
        if self.tokens_input < 0 or self.tokens_output < 0 or self.tokens_total < 0:
            raise ValueError("CompilerBatch token counts must be non-negative")


@dataclass(frozen=True, slots=True)
class SourceChunk:
    id: str
    document_id: str
    project_id: str
    source_index: int
    content: str
    page: int | None = None
    section_title: str = ""
    start_offset: int | None = None
    end_offset: int | None = None
    checksum: str = ""
    metadata: Metadata = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.source_index < 0:
            raise ValueError("SourceChunk.source_index must be non-negative")
        if not self.content.strip():
            raise ValueError("SourceChunk.content must not be blank")


@dataclass(frozen=True, slots=True)
class SourceRef:
    source_index: int | None = None
    quote: str = ""
    source_chunk_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        quote = " ".join(self.quote.strip().split())
        object.__setattr__(self, "quote", quote)

        if self.source_index is not None and self.source_index < 0:
            raise ValueError("SourceRef.source_index must be non-negative")
        if self.start_offset is not None and self.start_offset < 0:
            raise ValueError("SourceRef.start_offset must be non-negative")
        if self.end_offset is not None and self.end_offset < 0:
            raise ValueError("SourceRef.end_offset must be non-negative")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("SourceRef.end_offset must be >= start_offset")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("SourceRef.confidence must be between 0 and 1")

    @property
    def has_quote(self) -> bool:
        return bool(self.quote)

    @property
    def has_source_index(self) -> bool:
        return self.source_index is not None

    @property
    def has_source_chunk_id(self) -> bool:
        return bool(self.source_chunk_id)

    @property
    def has_offsets(self) -> bool:
        return self.start_offset is not None and self.end_offset is not None

    def is_grounded(self, *, minimum_level: int = 0) -> bool:
        if minimum_level <= 0:
            return self.has_quote
        if minimum_level == 1:
            return self.has_quote and self.has_source_index
        if minimum_level == 2:
            return self.has_quote and self.has_source_index
        return (
            self.has_quote
            and self.has_source_index
            and self.has_source_chunk_id
            and self.has_offsets
        )


@dataclass(frozen=True, slots=True)
class KnowledgeEnrichment:
    questions: tuple[str, ...] = ()
    paraphrases: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    typo_queries: tuple[str, ...] = ()
    colloquial_queries: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    retrieval_guards: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "questions", _clean_tuple(self.questions))
        object.__setattr__(self, "paraphrases", _clean_tuple(self.paraphrases))
        object.__setattr__(self, "synonyms", _clean_tuple(self.synonyms))
        object.__setattr__(self, "typo_queries", _clean_tuple(self.typo_queries))
        object.__setattr__(
            self,
            "colloquial_queries",
            _clean_tuple(self.colloquial_queries),
        )
        object.__setattr__(self, "tags", _clean_tuple(self.tags))
        object.__setattr__(
            self, "retrieval_guards", _clean_tuple(self.retrieval_guards)
        )

    @property
    def positive_query_surface(self) -> tuple[str, ...]:
        return (
            self.questions
            + self.paraphrases
            + self.synonyms
            + self.typo_queries
            + self.colloquial_queries
            + self.tags
        )


@dataclass(frozen=True, slots=True)
class EmbeddingText:
    value: str
    version: str

    def __post_init__(self) -> None:
        value = self.value.strip()
        version = self.version.strip()
        if not value:
            raise ValueError("EmbeddingText.value must not be blank")
        if not version:
            raise ValueError("EmbeddingText.version must not be blank")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "version", version)


@dataclass(frozen=True, slots=True)
class AnswerCandidate:
    id: str
    document_id: str
    project_id: str
    compiler_run_id: str
    topic_key: str
    title: str
    candidate_answer: str
    source_refs: tuple[SourceRef, ...] = ()
    confidence: float | None = None
    status: AnswerCandidateStatus = AnswerCandidateStatus.EXTRACTED
    rejection_reason: str = ""
    metadata: Metadata = field(default_factory=dict)
    created_at: datetime | None = None

    @property
    def has_grounding(self) -> bool:
        return any(ref.is_grounded(minimum_level=0) for ref in self.source_refs)


@dataclass(frozen=True, slots=True)
class CandidateCluster:
    id: str
    document_id: str
    project_id: str
    compiler_run_id: str
    cluster_key: str
    topic: str
    candidate_ids: tuple[str, ...]
    status: CandidateClusterStatus = CandidateClusterStatus.CREATED
    merge_strategy: str = ""
    merge_reason: str = ""
    metadata: Metadata = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CanonicalKnowledgeEntry:
    id: str
    project_id: str
    document_id: str
    compiler_run_id: str
    stable_key: str
    entry_kind: KnowledgeEntryKind
    title: str
    answer: str
    source_refs: tuple[SourceRef, ...]
    enrichment: KnowledgeEnrichment = field(default_factory=KnowledgeEnrichment)
    embedding_text: EmbeddingText | None = None
    status: KnowledgeEntryStatus = KnowledgeEntryStatus.DRAFT
    visibility: KnowledgeEntryVisibility = KnowledgeEntryVisibility.OWNER_ONLY
    version: int = 1
    compiler_version: str = ""
    embedding_text_version: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: Metadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        title = " ".join(self.title.strip().split())
        answer = " ".join(self.answer.strip().split())
        stable_key = self.stable_key.strip()

        if not stable_key:
            raise ValueError("CanonicalKnowledgeEntry.stable_key must not be blank")
        if not title:
            raise ValueError("CanonicalKnowledgeEntry.title must not be blank")
        if not answer:
            raise ValueError("CanonicalKnowledgeEntry.answer must not be blank")
        if self.version < 1:
            raise ValueError("CanonicalKnowledgeEntry.version must be positive")

        object.__setattr__(self, "title", title)
        object.__setattr__(self, "answer", answer)
        object.__setattr__(self, "stable_key", stable_key)

    @property
    def has_source_refs(self) -> bool:
        return any(ref.is_grounded(minimum_level=0) for ref in self.source_refs)

    @property
    def is_published_runtime_entry(self) -> bool:
        return (
            self.status == KnowledgeEntryStatus.PUBLISHED
            and self.visibility == KnowledgeEntryVisibility.RUNTIME
            and self.has_source_refs
        )

    def assert_publishable(self) -> None:
        if not self.has_source_refs:
            raise ValueError("Published CanonicalKnowledgeEntry requires source refs")
        if self.entry_kind == KnowledgeEntryKind.FALLBACK_CHUNK:
            raise ValueError("Fallback chunks require explicit fallback retrieval mode")


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    entry_id: str
    project_id: str
    document_id: str
    entry_kind: KnowledgeEntryKind
    title: str
    answer: str
    score: float | None = None
    method: str = ""
    source_refs: tuple[SourceRef, ...] = ()
    source_document_name: str = ""
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    project_id: str
    document_id: str
    question: str
    attack_type: str
    expected_answer: str = ""
    expected_entry_ids: tuple[str, ...] = ()
    expected_source_refs: tuple[SourceRef, ...] = ()
    should_answer: bool = True
    should_escalate: bool = False
    severity: str = "medium"
    status: EvalCaseStatus = EvalCaseStatus.GENERATED
    metadata: Metadata = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeEditAction:
    id: str
    project_id: str
    document_id: str
    actor_user_id: str
    action_type: str
    target_entry_id: str | None = None
    source_eval_case_id: str | None = None
    payload: Metadata = field(default_factory=dict)
    created_at: datetime | None = None


def _clean_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = " ".join(str(value).strip().split())
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        result.append(text)

    return tuple(result)
