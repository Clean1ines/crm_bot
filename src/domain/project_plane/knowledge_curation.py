from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from src.domain.project_plane.knowledge_compilation import (
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
)

JsonObject = dict[str, object]


class KnowledgeCurationIssueType(StrEnum):
    EMPTY_OR_TOO_SHORT_ANSWER = "empty_or_too_short_answer"
    MISSING_SOURCE_REFS = "missing_source_refs"
    DUPLICATE_TITLE = "duplicate_title"
    DUPLICATE_ANSWER = "duplicate_answer"
    SAME_STABLE_KEY = "same_stable_key"
    HIGH_ENRICHMENT_OVERLAP = "high_enrichment_overlap"
    SAME_SOURCE_QUOTE = "same_source_quote"
    TOO_FEW_QUESTIONS = "too_few_questions"
    TOO_MANY_QUESTIONS = "too_many_questions"
    FALLBACK_CHUNK = "fallback_chunk"
    NON_RUNTIME_STATUS = "non_runtime_status"
    PUBLISHED_WITHOUT_RETRIEVAL_ROW = "published_without_retrieval_row"
    NON_RUNTIME_WITH_RETRIEVAL_ROW = "non_runtime_with_retrieval_row"
    PUBLISHED_WITHOUT_EMBEDDING = "published_without_embedding"
    METADATA_ERRORS = "metadata_errors"
    MERGED_ABSORBED = "merged_absorbed"


class KnowledgeCurationActionType(StrEnum):
    MERGE_ENTRIES = "merge_entries"
    HIDE_ENTRY = "hide_entry"
    REJECT_ENTRY = "reject_entry"
    RESTORE_ENTRY = "restore_entry"
    PUBLISH_ENTRY = "publish_entry"
    UNPUBLISH_ENTRY = "unpublish_entry"
    EDIT_ENTRY_TITLE = "edit_entry_title"
    EDIT_ENTRY_ANSWER = "edit_entry_answer"
    EDIT_ENTRY_ENRICHMENT = "edit_entry_enrichment"
    REBUILD_EMBEDDING = "rebuild_embedding"
    RERUN_EVAL = "rerun_eval"


class KnowledgeCurationActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"
    APPLIED_WITH_WARNING = "applied_with_warning"


@dataclass(frozen=True, slots=True)
class KnowledgeCurationIssue:
    type: KnowledgeCurationIssueType
    severity: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeCurationEntryView:
    id: str
    project_id: str
    document_id: str
    stable_key: str
    entry_kind: KnowledgeEntryKind
    title: str
    answer: str
    status: KnowledgeEntryStatus
    visibility: KnowledgeEntryVisibility
    version: int
    enrichment: Mapping[str, object]
    source_refs: tuple[Mapping[str, object], ...]
    metadata: Mapping[str, object]
    has_retrieval_surface: bool
    has_embedding: bool
    runtime_eligible: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    issues: tuple[KnowledgeCurationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeCurationSummary:
    document_id: str
    document_name: str
    document_status: str
    processing_stage: str
    total_entries: int
    published_runtime_entries: int
    needs_review_entries: int
    hidden_entries: int
    rejected_entries: int
    merged_entries: int
    duplicate_group_count: int
    entries_without_source_refs: int
    entries_missing_retrieval_surface: int
    suspicious_entries: int
    document_processing_active: bool


@dataclass(frozen=True, slots=True)
class KnowledgeCurationDuplicateGroup:
    group_id: str
    reason: str
    issue_type: KnowledgeCurationIssueType
    entry_ids: tuple[str, ...]
    score: float
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeEntryStatusTransition:
    action: KnowledgeCurationActionType
    target_status: KnowledgeEntryStatus | None = None
    target_visibility: KnowledgeEntryVisibility | None = None
    expected_version: int | None = None
    reason: str = ""
    rebuild_embedding: bool = False
    rerun_eval: bool = False
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeEntryPatch:
    title: str | None = None
    answer: str | None = None
    enrichment: Mapping[str, object] | None = None
    source_refs: tuple[Mapping[str, object], ...] | None = None
    expected_version: int | None = None
    reason: str = ""
    rebuild_embedding: bool = False
    rerun_eval: bool = False
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeEntryMergeIncludeOptions:
    answers: bool = True
    questions: bool = True
    paraphrases: bool = True
    synonyms: bool = True
    typo_queries: bool = True
    colloquial_queries: bool = True
    tags: bool = True
    retrieval_guards: bool = False
    source_refs: bool = True
    metadata: bool = True


@dataclass(frozen=True, slots=True)
class KnowledgeEntryMergeExcludeOptions:
    question_values: tuple[str, ...] = ()
    synonym_values: tuple[str, ...] = ()
    tag_values: tuple[str, ...] = ()
    source_ref_keys: tuple[str, ...] = ()
    metadata_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeEntryMergeRequest:
    parent_entry_id: str
    absorbed_entry_ids: tuple[str, ...]
    parent_expected_version: int | None = None
    absorbed_expected_versions: Mapping[str, int] = field(default_factory=dict)
    merge_instruction: str = ""
    final_title: str | None = None
    final_answer: str | None = None
    include: KnowledgeEntryMergeIncludeOptions = field(
        default_factory=KnowledgeEntryMergeIncludeOptions
    )
    exclude: KnowledgeEntryMergeExcludeOptions = field(
        default_factory=KnowledgeEntryMergeExcludeOptions
    )
    absorbed_status: str = "merged"
    rebuild_embedding: bool = True
    rerun_eval: bool = False
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeEntryMergePreview:
    parent_entry_before: KnowledgeCurationEntryView
    absorbed_entries_before: tuple[KnowledgeCurationEntryView, ...]
    proposed_entry_after: Mapping[str, object]
    absorbed_entries_after: tuple[Mapping[str, object], ...]
    included_counts: Mapping[str, int]
    excluded_counts: Mapping[str, int]
    warnings: tuple[str, ...]
    blocking_errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeEntryMergeApplyResult:
    ok: bool
    partial: bool
    action_id: str
    parent_entry_id: str
    absorbed_entry_ids: tuple[str, ...]
    parent_version: int
    embedding_rebuilt: bool
    rerun_eval_enqueued: bool
    error: str = ""
    preview: KnowledgeEntryMergePreview | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeEntryVersionView:
    id: str
    entry_id: str
    project_id: str
    document_id: str | None
    action_id: str | None
    from_version: int
    to_version: int
    previous_snapshot: Mapping[str, object]
    new_snapshot: Mapping[str, object]
    created_at: datetime | None = None


def is_absorbed_merged_entry(entry: KnowledgeCurationEntryView) -> bool:
    curation = entry.metadata.get("curation")
    if isinstance(curation, Mapping) and curation.get("merged_into"):
        return True
    return entry.status.value == "merged"
