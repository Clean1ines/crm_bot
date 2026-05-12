from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
)


TRANSITIONAL_PRODUCTION_ENTRY_TYPES = frozenset(
    {
        "answer_knowledge",
        "faq",
        "price_list",
        "instruction",
    }
)

TRANSITIONAL_FALLBACK_ENTRY_TYPES = frozenset(
    {
        "chunk",
        "fallback_chunk",
        "source_fallback",
        "legacy_plain_chunk",
    }
)

FORBIDDEN_PRODUCTION_ENTRY_TYPES = frozenset(
    {
        "internal_eval_test",
        "negative_test",
        "retrieval_guideline",
        "eval_question",
        "adversarial_question",
        "judge_prompt",
        "judge_output",
        "regression_test",
        "debug",
        "debug_artifact",
        "generated_question",
        "generated_synonym",
        "generated_paraphrase",
        "typo_query",
        "prompt",
        "system_prompt",
        "developer_prompt",
    }
)

RUNTIME_ENTRY_KINDS = frozenset(
    {
        KnowledgeEntryKind.ANSWER,
        KnowledgeEntryKind.FAQ_ANSWER,
        KnowledgeEntryKind.CONTACT_INFO,
        KnowledgeEntryKind.WORKING_HOURS,
        KnowledgeEntryKind.CATALOG_ANSWER,
        KnowledgeEntryKind.PRICE_ANSWER,
        KnowledgeEntryKind.PRICING_POLICY,
        KnowledgeEntryKind.REFUND_POLICY,
        KnowledgeEntryKind.DELIVERY_POLICY,
        KnowledgeEntryKind.POLICY_CLAUSE,
        KnowledgeEntryKind.PROCEDURE,
        KnowledgeEntryKind.WARNING,
        KnowledgeEntryKind.REQUIREMENT,
        KnowledgeEntryKind.TROUBLESHOOTING_STEP,
        KnowledgeEntryKind.CUSTOM,
    }
)


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceEligibility:
    allowed: bool
    reason: str


def normalize_entry_classifier(value: object) -> str:
    return str(value or "").strip().lower()


def is_forbidden_runtime_artifact(value: object) -> bool:
    classifier = normalize_entry_classifier(value)
    return classifier in FORBIDDEN_PRODUCTION_ENTRY_TYPES


def is_transitional_production_entry_type(value: object) -> bool:
    classifier = normalize_entry_classifier(value)
    return classifier in TRANSITIONAL_PRODUCTION_ENTRY_TYPES


def is_transitional_fallback_entry_type(value: object) -> bool:
    classifier = normalize_entry_classifier(value)
    return classifier in TRANSITIONAL_FALLBACK_ENTRY_TYPES


def is_runtime_entry_kind(value: object) -> bool:
    classifier = normalize_entry_classifier(value)
    return any(classifier == kind.value for kind in RUNTIME_ENTRY_KINDS)


def is_compiler_mode_not_entry_kind(value: object) -> bool:
    classifier = normalize_entry_classifier(value)
    return classifier in {"plain", "faq", "price_list", "instruction"}


def transitional_runtime_row_eligibility(
    entry_type: object,
    *,
    has_source_evidence: bool,
    fallback_raw_search_enabled: bool = False,
) -> RetrievalSurfaceEligibility:
    classifier = normalize_entry_classifier(entry_type)

    if not classifier:
        return RetrievalSurfaceEligibility(False, "entry_type_missing")

    if is_forbidden_runtime_artifact(classifier):
        return RetrievalSurfaceEligibility(False, "forbidden_runtime_artifact")

    if is_transitional_production_entry_type(classifier):
        if not has_source_evidence:
            return RetrievalSurfaceEligibility(False, "source_evidence_required")
        return RetrievalSurfaceEligibility(True, "transitional_production_entry")

    if is_transitional_fallback_entry_type(classifier):
        if not fallback_raw_search_enabled:
            return RetrievalSurfaceEligibility(False, "fallback_not_enabled")
        if not has_source_evidence:
            return RetrievalSurfaceEligibility(False, "source_evidence_required")
        return RetrievalSurfaceEligibility(True, "explicit_fallback_entry")

    return RetrievalSurfaceEligibility(False, "not_in_retrieval_surface")


def is_transitional_runtime_row(
    entry_type: object,
    *,
    has_source_evidence: bool,
    fallback_raw_search_enabled: bool = False,
) -> bool:
    return transitional_runtime_row_eligibility(
        entry_type,
        has_source_evidence=has_source_evidence,
        fallback_raw_search_enabled=fallback_raw_search_enabled,
    ).allowed


def canonical_entry_eligibility(
    entry: CanonicalKnowledgeEntry,
    *,
    fallback_raw_search_enabled: bool = False,
) -> RetrievalSurfaceEligibility:
    if entry.status != KnowledgeEntryStatus.PUBLISHED:
        return RetrievalSurfaceEligibility(False, "entry_not_published")

    if entry.visibility != KnowledgeEntryVisibility.RUNTIME:
        return RetrievalSurfaceEligibility(False, "entry_not_runtime_visible")

    if entry.entry_kind == KnowledgeEntryKind.FALLBACK_CHUNK:
        if not fallback_raw_search_enabled:
            return RetrievalSurfaceEligibility(False, "fallback_not_enabled")

    elif entry.entry_kind not in RUNTIME_ENTRY_KINDS:
        return RetrievalSurfaceEligibility(False, "entry_kind_not_runtime_safe")

    if not entry.has_source_refs:
        return RetrievalSurfaceEligibility(False, "source_refs_required")

    return RetrievalSurfaceEligibility(True, "canonical_runtime_entry")


def is_canonical_runtime_entry(
    entry: CanonicalKnowledgeEntry,
    *,
    fallback_raw_search_enabled: bool = False,
) -> bool:
    return canonical_entry_eligibility(
        entry,
        fallback_raw_search_enabled=fallback_raw_search_enabled,
    ).allowed


def filter_canonical_runtime_entries(
    entries: Iterable[CanonicalKnowledgeEntry],
    *,
    fallback_raw_search_enabled: bool = False,
) -> tuple[CanonicalKnowledgeEntry, ...]:
    return tuple(
        entry
        for entry in entries
        if is_canonical_runtime_entry(
            entry,
            fallback_raw_search_enabled=fallback_raw_search_enabled,
        )
    )
