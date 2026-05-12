from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
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

RUNTIME_ENTRY_KIND_VALUES = frozenset(kind.value for kind in RUNTIME_ENTRY_KINDS)
COMPILER_MODE_VALUES = frozenset({"plain", "faq", "price_list", "instruction"})


@dataclass(frozen=True, slots=True)
class RetrievalSurfaceEligibility:
    allowed: bool
    reason: str


def normalize_entry_classifier(value: object) -> str:
    return str(value or "").strip().lower()


def is_runtime_entry_kind(value: object) -> bool:
    return normalize_entry_classifier(value) in RUNTIME_ENTRY_KIND_VALUES


def is_compiler_mode_not_entry_kind(value: object) -> bool:
    return normalize_entry_classifier(value) in COMPILER_MODE_VALUES


def canonical_entry_eligibility(
    entry: CanonicalKnowledgeEntry,
) -> RetrievalSurfaceEligibility:
    if entry.status != KnowledgeEntryStatus.PUBLISHED:
        return RetrievalSurfaceEligibility(False, "entry_not_published")

    if entry.visibility != KnowledgeEntryVisibility.RUNTIME:
        return RetrievalSurfaceEligibility(False, "entry_not_runtime_visible")

    if entry.entry_kind not in RUNTIME_ENTRY_KINDS:
        return RetrievalSurfaceEligibility(False, "entry_kind_not_runtime_safe")

    if not entry.has_source_refs:
        return RetrievalSurfaceEligibility(False, "source_refs_required")

    return RetrievalSurfaceEligibility(True, "canonical_runtime_entry")


def is_canonical_runtime_entry(entry: CanonicalKnowledgeEntry) -> bool:
    return canonical_entry_eligibility(entry).allowed


def filter_canonical_runtime_entries(
    entries: Iterable[CanonicalKnowledgeEntry],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    return tuple(entry for entry in entries if is_canonical_runtime_entry(entry))
