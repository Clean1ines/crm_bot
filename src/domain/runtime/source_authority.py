from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from src.domain.runtime.evidence import (
    EvidenceFreshness,
    EvidenceItem,
    EvidenceSourceType,
)


class SourceAuthorityRank(IntEnum):
    LLM_REASONING = 0
    USER_MESSAGE = 20
    CONVERSATION_MEMORY = 30
    COMPILED_KNOWLEDGE = 50
    COMPILED_PRICE_LIST = 60
    TOOL_RESULT = 70
    CATALOG_OPERATIONAL = 80
    CRM_OPERATIONAL = 90
    MANAGER_OVERRIDE = 100


class SourceConflictStrategy(StrEnum):
    PREFER_HIGHER_AUTHORITY = "prefer_higher_authority"
    REQUIRE_HUMAN_REVIEW = "require_human_review"
    DISCLOSE_UNCERTAINTY = "disclose_uncertainty"


SOURCE_AUTHORITY_RANKS: Mapping[EvidenceSourceType, SourceAuthorityRank] = {
    EvidenceSourceType.LLM_REASONING: SourceAuthorityRank.LLM_REASONING,
    EvidenceSourceType.USER_MESSAGE: SourceAuthorityRank.USER_MESSAGE,
    EvidenceSourceType.CONVERSATION_MEMORY: SourceAuthorityRank.CONVERSATION_MEMORY,
    EvidenceSourceType.COMPILED_KNOWLEDGE: SourceAuthorityRank.COMPILED_KNOWLEDGE,
    EvidenceSourceType.COMPILED_PRICE_LIST: SourceAuthorityRank.COMPILED_PRICE_LIST,
    EvidenceSourceType.TOOL_RESULT: SourceAuthorityRank.TOOL_RESULT,
    EvidenceSourceType.CATALOG_OPERATIONAL: SourceAuthorityRank.CATALOG_OPERATIONAL,
    EvidenceSourceType.CRM_OPERATIONAL: SourceAuthorityRank.CRM_OPERATIONAL,
    EvidenceSourceType.MANAGER_OVERRIDE: SourceAuthorityRank.MANAGER_OVERRIDE,
}

FRESHNESS_RANKS: Mapping[EvidenceFreshness, int] = {
    EvidenceFreshness.LIVE: 50,
    EvidenceFreshness.CURRENT: 40,
    EvidenceFreshness.SNAPSHOT: 30,
    EvidenceFreshness.UNKNOWN: 10,
    EvidenceFreshness.STALE: 0,
}


@dataclass(frozen=True, slots=True)
class SourceAuthorityDecision:
    preferred: EvidenceItem | None
    rejected: tuple[EvidenceItem, ...] = ()
    reason: str = ""
    conflict_detected: bool = False
    requires_human_review: bool = False
    strategy: SourceConflictStrategy = SourceConflictStrategy.PREFER_HIGHER_AUTHORITY


class SourceAuthorityPolicy:
    """Pure source-priority policy for answer-time evidence.

    It does not execute tools, read databases, or call LLMs.
    """

    def rank_source_type(self, source_type: EvidenceSourceType) -> SourceAuthorityRank:
        return SOURCE_AUTHORITY_RANKS[source_type]

    def rank_evidence(self, item: EvidenceItem) -> tuple[int, int, float]:
        return (
            int(self.rank_source_type(item.source_type)),
            FRESHNESS_RANKS[item.freshness],
            item.confidence,
        )

    def select_preferred(
        self,
        items: Sequence[EvidenceItem],
        *,
        strategy: SourceConflictStrategy = SourceConflictStrategy.PREFER_HIGHER_AUTHORITY,
    ) -> SourceAuthorityDecision:
        authoritative = tuple(item for item in items if item.is_authoritative)
        if not authoritative:
            return SourceAuthorityDecision(
                preferred=None,
                rejected=tuple(items),
                reason="no_authoritative_evidence",
                conflict_detected=bool(items),
                requires_human_review=bool(items),
                strategy=strategy,
            )

        ordered = tuple(
            sorted(
                authoritative,
                key=self.rank_evidence,
                reverse=True,
            )
        )
        preferred = ordered[0]
        rejected = ordered[1:]
        conflict_detected = _has_content_conflict(ordered)

        if (
            conflict_detected
            and strategy == SourceConflictStrategy.REQUIRE_HUMAN_REVIEW
        ):
            return SourceAuthorityDecision(
                preferred=preferred,
                rejected=rejected,
                reason="conflicting_authoritative_evidence_requires_review",
                conflict_detected=True,
                requires_human_review=True,
                strategy=strategy,
            )

        return SourceAuthorityDecision(
            preferred=preferred,
            rejected=rejected,
            reason="selected_highest_authority_evidence",
            conflict_detected=conflict_detected,
            requires_human_review=False,
            strategy=strategy,
        )


def _has_content_conflict(items: Sequence[EvidenceItem]) -> bool:
    by_key: dict[str, set[str]] = {}
    for item in items:
        key = item.normalized_fact_key
        if key is None:
            continue
        normalized_content = " ".join(item.content.strip().lower().split())
        if not normalized_content:
            continue
        by_key.setdefault(key, set()).add(normalized_content)

    return any(len(contents) > 1 for contents in by_key.values())
