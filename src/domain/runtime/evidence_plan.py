from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from src.domain.commercial.price_query import PriceQueryIntent, PriceQueryResolution
from src.domain.runtime.evidence import (
    EvidenceBundle,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceSourceType,
)
from src.domain.runtime.source_authority import (
    SourceAuthorityDecision,
    SourceAuthorityPolicy,
    SourceConflictStrategy,
)


class EvidenceNeedKind(StrEnum):
    COMPILED_KNOWLEDGE = "compiled_knowledge"
    COMPILED_PRICE_LIST = "compiled_price_list"
    LIVE_OPERATIONAL = "live_operational"
    CLARIFICATION = "clarification"


class EvidencePlanStatus(StrEnum):
    READY = "ready"
    NEEDS_EVIDENCE = "needs_evidence"
    NEEDS_CLARIFICATION = "needs_clarification"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


@dataclass(frozen=True, slots=True)
class EvidenceNeed:
    kind: EvidenceNeedKind
    source_types: tuple[EvidenceSourceType, ...] = ()
    requires_live_freshness: bool = False
    missing_slots: tuple[str, ...] = ()
    reason: str = ""

    def is_satisfied_by(self, item: EvidenceItem) -> bool:
        if item.source_type not in self.source_types:
            return False
        if not item.is_authoritative:
            return False
        if self.requires_live_freshness:
            return item.freshness in {EvidenceFreshness.LIVE, EvidenceFreshness.CURRENT}
        return True


@dataclass(frozen=True, slots=True)
class EvidencePlan:
    needs: tuple[EvidenceNeed, ...]
    conflict_strategy: SourceConflictStrategy = (
        SourceConflictStrategy.PREFER_HIGHER_AUTHORITY
    )
    reason: str = ""

    @classmethod
    def for_stable_faq(cls) -> "EvidencePlan":
        return cls(
            needs=(
                EvidenceNeed(
                    kind=EvidenceNeedKind.COMPILED_KNOWLEDGE,
                    source_types=(EvidenceSourceType.COMPILED_KNOWLEDGE,),
                    reason="stable_faq_requires_compiled_knowledge",
                ),
            ),
            reason="stable_faq",
        )

    @classmethod
    def for_price_query_resolution(
        cls,
        resolution: PriceQueryResolution,
        *,
        conflict_strategy: SourceConflictStrategy = (
            SourceConflictStrategy.PREFER_HIGHER_AUTHORITY
        ),
    ) -> "EvidencePlan":
        if resolution.needs_clarification:
            return cls(
                needs=(
                    EvidenceNeed(
                        kind=EvidenceNeedKind.CLARIFICATION,
                        missing_slots=resolution.missing_slots,
                        reason="commercial_query_requires_clarification",
                    ),
                ),
                conflict_strategy=conflict_strategy,
                reason="commercial_clarification_required",
            )

        query = resolution.query
        if query.intent == PriceQueryIntent.AVAILABILITY_QUERY:
            return cls(
                needs=(
                    EvidenceNeed(
                        kind=EvidenceNeedKind.LIVE_OPERATIONAL,
                        source_types=(
                            EvidenceSourceType.CATALOG_OPERATIONAL,
                            EvidenceSourceType.CRM_OPERATIONAL,
                        ),
                        requires_live_freshness=True,
                        reason="availability_requires_live_operational_evidence",
                    ),
                ),
                conflict_strategy=conflict_strategy,
                reason="availability_query",
            )

        if query.requires_live_operational_source:
            return cls(
                needs=(
                    EvidenceNeed(
                        kind=EvidenceNeedKind.LIVE_OPERATIONAL,
                        source_types=(EvidenceSourceType.CRM_OPERATIONAL,),
                        requires_live_freshness=True,
                        reason="commercial_query_requires_live_crm_evidence",
                    ),
                ),
                conflict_strategy=conflict_strategy,
                reason="commercial_live_operational_query",
            )

        return cls(
            needs=(
                EvidenceNeed(
                    kind=EvidenceNeedKind.COMPILED_PRICE_LIST,
                    source_types=(EvidenceSourceType.COMPILED_PRICE_LIST,),
                    reason="commercial_query_requires_compiled_price_list",
                ),
            ),
            conflict_strategy=conflict_strategy,
            reason="commercial_snapshot_query",
        )

    @property
    def required_source_types(self) -> tuple[EvidenceSourceType, ...]:
        result: list[EvidenceSourceType] = []
        for need in self.needs:
            for source_type in need.source_types:
                if source_type not in result:
                    result.append(source_type)
        return tuple(result)

    @property
    def missing_slots(self) -> tuple[str, ...]:
        result: list[str] = []
        for need in self.needs:
            for slot in need.missing_slots:
                if slot not in result:
                    result.append(slot)
        return tuple(result)

    @property
    def requires_live_operational_source(self) -> bool:
        return any(need.requires_live_freshness for need in self.needs)

    def decide(
        self,
        evidence: EvidenceBundle,
        *,
        authority_policy: SourceAuthorityPolicy | None = None,
    ) -> "EvidencePlanDecision":
        clarification_needs = tuple(
            need for need in self.needs if need.kind == EvidenceNeedKind.CLARIFICATION
        )
        if clarification_needs:
            clarification_slots = self.missing_slots
            reason = (
                "missing_required_slots"
                if clarification_slots
                else "commercial_query_requires_clarification"
            )
            return EvidencePlanDecision(
                plan=self,
                status=EvidencePlanStatus.NEEDS_CLARIFICATION,
                missing_needs=clarification_needs,
                missing_slots=clarification_slots,
                reason=reason,
            )

        policy = authority_policy or SourceAuthorityPolicy()
        if evidence.items and not evidence.authoritative_items():
            authority_decision = policy.select_preferred(
                evidence.items,
                strategy=self.conflict_strategy,
            )
            return EvidencePlanDecision(
                plan=self,
                status=EvidencePlanStatus.REQUIRES_HUMAN_REVIEW,
                authority_decision=authority_decision,
                reason="no_authoritative_evidence",
            )

        satisfied_items = _satisfied_items(self.needs, evidence.items)
        missing_needs = tuple(
            need
            for need in self.needs
            if not any(need.is_satisfied_by(item) for item in evidence.items)
        )
        if missing_needs:
            status = EvidencePlanStatus.NEEDS_EVIDENCE
            reason = "missing_required_evidence"
            if any(need.requires_live_freshness for need in missing_needs):
                status = EvidencePlanStatus.REQUIRES_HUMAN_REVIEW
                reason = "missing_required_live_operational_evidence"
            return EvidencePlanDecision(
                plan=self,
                status=status,
                missing_needs=missing_needs,
                reason=reason,
            )

        authority_decision = policy.select_preferred(
            satisfied_items,
            strategy=self.conflict_strategy,
        )
        if authority_decision.requires_human_review:
            return EvidencePlanDecision(
                plan=self,
                status=EvidencePlanStatus.REQUIRES_HUMAN_REVIEW,
                authority_decision=authority_decision,
                reason=authority_decision.reason,
            )
        if authority_decision.preferred is None:
            return EvidencePlanDecision(
                plan=self,
                status=EvidencePlanStatus.REQUIRES_HUMAN_REVIEW,
                authority_decision=authority_decision,
                reason="no_authoritative_evidence",
            )

        return EvidencePlanDecision(
            plan=self,
            status=EvidencePlanStatus.READY,
            authority_decision=authority_decision,
            reason="required_evidence_ready",
        )


@dataclass(frozen=True, slots=True)
class EvidencePlanDecision:
    plan: EvidencePlan
    status: EvidencePlanStatus
    authority_decision: SourceAuthorityDecision | None = None
    missing_needs: tuple[EvidenceNeed, ...] = ()
    missing_slots: tuple[str, ...] = ()
    reason: str = ""

    @property
    def answer_may_proceed(self) -> bool:
        return self.status == EvidencePlanStatus.READY

    @property
    def requires_human_review(self) -> bool:
        return self.status == EvidencePlanStatus.REQUIRES_HUMAN_REVIEW

    @property
    def needs_clarification(self) -> bool:
        return self.status == EvidencePlanStatus.NEEDS_CLARIFICATION


@dataclass(frozen=True, slots=True)
class AnswerEvidencePlan:
    plan: EvidencePlan
    decision: EvidencePlanDecision | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


def _satisfied_items(
    needs: Sequence[EvidenceNeed],
    items: Sequence[EvidenceItem],
) -> tuple[EvidenceItem, ...]:
    result: list[EvidenceItem] = []
    for item in items:
        if item in result:
            continue
        if any(need.is_satisfied_by(item) for need in needs):
            result.append(item)
    return tuple(result)
