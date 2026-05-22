from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.domain.commercial.commercial_truth import (
    CommercialConflictResolution,
    CommercialConflictResolutionStatus,
    CommercialFactSnapshot,
    CommercialSourceDescriptor,
    CommercialSourceKind,
    CommercialTruthResolutionPolicy,
    commercial_retrieval_surface_facts,
    detect_commercial_fact_conflicts,
    resolve_commercial_conflict_by_policy,
)
from src.domain.commercial.pricing import MoneyAmount
from src.domain.project_plane.knowledge_views import KnowledgeDocumentDetailView
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PublishedPriceFact,
)


@dataclass(frozen=True, slots=True)
class CommercialTruthFactReviewDto:
    fact_id: str
    price_document_id: str
    item_name: str
    value_kind: str
    status: str
    unit: str
    value_text: str
    source_quote: str
    source_id: str
    source_kind: str
    source_authority: str
    is_runtime_eligible: bool

    @classmethod
    def from_snapshot(
        cls,
        snapshot: CommercialFactSnapshot,
    ) -> "CommercialTruthFactReviewDto":
        return cls(
            fact_id=snapshot.fact.id,
            price_document_id=snapshot.fact.price_document_id,
            item_name=snapshot.fact.item_name,
            value_kind=snapshot.fact.value_kind.value,
            status=snapshot.fact.status.value,
            unit=snapshot.fact.unit,
            value_text=commercial_truth_fact_value_text(snapshot.fact),
            source_quote=commercial_truth_source_quote(snapshot.fact),
            source_id=snapshot.source.id,
            source_kind=snapshot.source.kind.value,
            source_authority=snapshot.source.effective_authority.value,
            is_runtime_eligible=snapshot.fact.is_runtime_eligible,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "fact_id": self.fact_id,
            "price_document_id": self.price_document_id,
            "item_name": self.item_name,
            "value_kind": self.value_kind,
            "status": self.status,
            "unit": self.unit,
            "value_text": self.value_text,
            "source_quote": self.source_quote,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "source_authority": self.source_authority,
            "is_runtime_eligible": self.is_runtime_eligible,
        }


@dataclass(frozen=True, slots=True)
class CommercialTruthConflictReviewDto:
    identity_key: str
    reason: str
    resolution_status: str
    resolution_reason: str
    selected_fact_id: str | None
    options: tuple[CommercialTruthFactReviewDto, ...]

    @classmethod
    def from_resolution(
        cls,
        resolution: CommercialConflictResolution,
    ) -> "CommercialTruthConflictReviewDto":
        selected_fact_id = (
            resolution.selected_snapshot.fact.id
            if resolution.selected_snapshot is not None
            else None
        )
        return cls(
            identity_key=commercial_fact_identity_key(
                resolution.group.identity.normalized_item_name,
                resolution.group.identity.normalized_unit,
                resolution.group.identity.normalized_variant,
            ),
            reason=resolution.group.reason.value,
            resolution_status=resolution.status.value,
            resolution_reason=resolution.reason,
            selected_fact_id=selected_fact_id,
            options=tuple(
                CommercialTruthFactReviewDto.from_snapshot(snapshot)
                for snapshot in resolution.group.snapshots
            ),
        )

    @property
    def is_resolved(self) -> bool:
        return (
            self.resolution_status
            == CommercialConflictResolutionStatus.RESOLVED_BY_POLICY.value
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "identity_key": self.identity_key,
            "reason": self.reason,
            "resolution_status": self.resolution_status,
            "resolution_reason": self.resolution_reason,
            "selected_fact_id": self.selected_fact_id,
            "options": [option.to_dict() for option in self.options],
        }


@dataclass(frozen=True, slots=True)
class CommercialTruthReviewReport:
    policy: CommercialTruthResolutionPolicy
    facts: tuple[CommercialTruthFactReviewDto, ...]
    conflicts: tuple[CommercialTruthConflictReviewDto, ...]
    surface_facts: tuple[PublishedPriceFact, ...]

    @property
    def fact_count(self) -> int:
        return len(self.facts)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    @property
    def resolved_conflict_count(self) -> int:
        return sum(1 for conflict in self.conflicts if conflict.is_resolved)

    @property
    def unresolved_conflict_count(self) -> int:
        return self.conflict_count - self.resolved_conflict_count

    @property
    def surface_fact_ids(self) -> tuple[str, ...]:
        return tuple(fact.id for fact in self.surface_facts)

    @property
    def surface_fact_reviews(self) -> tuple[CommercialTruthFactReviewDto, ...]:
        reviews_by_fact_id = {fact.fact_id: fact for fact in self.facts}
        return tuple(
            reviews_by_fact_id[fact_id]
            for fact_id in self.surface_fact_ids
            if fact_id in reviews_by_fact_id
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy.value,
            "fact_count": self.fact_count,
            "conflict_count": self.conflict_count,
            "resolved_conflict_count": self.resolved_conflict_count,
            "unresolved_conflict_count": self.unresolved_conflict_count,
            "surface_fact_ids": list(self.surface_fact_ids),
            "surface_facts": [fact.to_dict() for fact in self.surface_fact_reviews],
            "facts": [fact.to_dict() for fact in self.facts],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }


def commercial_truth_fact_value_text(fact: PublishedPriceFact) -> str:
    if fact.amount is not None:
        return _money_text(fact.amount)

    if fact.price_range is not None:
        return (
            f"{_money_text(fact.price_range.min_amount)} – "
            f"{_money_text(fact.price_range.max_amount)}"
        )

    if fact.price_text.strip():
        return fact.price_text

    return fact.value_kind.value


def commercial_truth_source_quote(fact: PublishedPriceFact) -> str:
    for source_ref in fact.source_refs:
        if source_ref.quote.strip():
            return source_ref.quote
    return ""


def _money_text(amount: MoneyAmount) -> str:
    return f"{_decimal_text(amount.amount)} {amount.currency}"


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def commercial_source_descriptor_from_price_document(
    document: PriceDocument,
    *,
    knowledge_document: KnowledgeDocumentDetailView | None = None,
) -> CommercialSourceDescriptor:
    return CommercialSourceDescriptor(
        id=document.id,
        kind=commercial_source_kind_from_price_document(
            document,
            knowledge_document=knowledge_document,
        ),
        title=_commercial_source_title(document, knowledge_document),
        observed_at=_commercial_source_observed_at(knowledge_document),
    )


def commercial_source_kind_from_price_document(
    document: PriceDocument,
    *,
    knowledge_document: KnowledgeDocumentDetailView | None = None,
) -> CommercialSourceKind:
    preprocessing_mode = _knowledge_document_preprocessing_mode(knowledge_document)
    if preprocessing_mode == "price_list":
        return CommercialSourceKind.STRUCTURED_PRICE_LIST
    if preprocessing_mode == "faq":
        return CommercialSourceKind.FAQ
    if preprocessing_mode in {"instruction", "plain"}:
        return CommercialSourceKind.DOCUMENT

    if document.source_format in {
        PriceDocumentSourceFormat.CSV,
        PriceDocumentSourceFormat.XLSX,
        PriceDocumentSourceFormat.PDF_TABLE,
    }:
        return CommercialSourceKind.STRUCTURED_PRICE_LIST

    if document.input_kind == PriceDocumentInputKind.TABLE:
        return CommercialSourceKind.STRUCTURED_PRICE_LIST

    if document.input_kind in {
        PriceDocumentInputKind.STRUCTURED_TEXT,
        PriceDocumentInputKind.MIXED,
    }:
        return CommercialSourceKind.COMMERCIAL_OFFER

    if document.input_kind == PriceDocumentInputKind.UNSTRUCTURED_TEXT:
        return CommercialSourceKind.DOCUMENT

    return CommercialSourceKind.UNKNOWN


def _knowledge_document_preprocessing_mode(
    knowledge_document: KnowledgeDocumentDetailView | None,
) -> str:
    if knowledge_document is None or knowledge_document.preprocessing_mode is None:
        return ""
    return str(knowledge_document.preprocessing_mode).strip().lower()


def _commercial_source_title(
    document: PriceDocument,
    knowledge_document: KnowledgeDocumentDetailView | None,
) -> str:
    if knowledge_document is not None and knowledge_document.file_name.strip():
        return knowledge_document.file_name
    return document.knowledge_document_id


def _commercial_source_observed_at(
    knowledge_document: KnowledgeDocumentDetailView | None,
) -> datetime | None:
    if knowledge_document is None:
        return None
    return _parse_observed_at(knowledge_document.created_at)


def _parse_observed_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


class CommercialTruthReviewService:
    """Builds a commercial truth review report from extracted price facts.

    This service is intentionally application-only orchestration. It does not
    persist conflicts, publish facts, call runtime lookup, or reach into HTTP/DB.
    """

    def review_price_facts(
        self,
        *,
        facts: Sequence[PublishedPriceFact],
        sources_by_price_document_id: Mapping[str, CommercialSourceDescriptor],
        policy: CommercialTruthResolutionPolicy = (
            CommercialTruthResolutionPolicy.MANUAL_REVIEW
        ),
    ) -> CommercialTruthReviewReport:
        snapshots = tuple(
            CommercialFactSnapshot(
                fact=fact,
                source=sources_by_price_document_id.get(
                    fact.price_document_id,
                    self._default_source_for_fact(fact),
                ),
            )
            for fact in facts
        )
        conflicts = detect_commercial_fact_conflicts(snapshots)
        resolutions = tuple(
            resolve_commercial_conflict_by_policy(conflict, policy)
            for conflict in conflicts
        )
        surface_facts = commercial_retrieval_surface_facts(
            snapshots,
            policy=policy,
        )

        return CommercialTruthReviewReport(
            policy=policy,
            facts=tuple(
                CommercialTruthFactReviewDto.from_snapshot(snapshot)
                for snapshot in snapshots
            ),
            conflicts=tuple(
                CommercialTruthConflictReviewDto.from_resolution(resolution)
                for resolution in resolutions
            ),
            surface_facts=surface_facts,
        )

    def _default_source_for_fact(
        self,
        fact: PublishedPriceFact,
    ) -> CommercialSourceDescriptor:
        return CommercialSourceDescriptor(
            id=fact.price_document_id,
            kind=CommercialSourceKind.UNKNOWN,
            title=fact.price_document_id,
        )


def commercial_fact_identity_key(
    normalized_item_name: str,
    normalized_unit: str,
    normalized_variant: tuple[tuple[str, str], ...],
) -> str:
    variant_text = ",".join(f"{key}={value}" for key, value in normalized_variant)
    return "|".join(
        item
        for item in (
            normalized_item_name,
            normalized_unit,
            variant_text,
        )
        if item
    )
