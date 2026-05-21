from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from src.domain.commercial.pricing import (
    MoneyAmount,
    normalize_slot_name,
    normalize_slot_value,
)


class PriceDocumentSourceFormat(StrEnum):
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
    CSV = "csv"
    XLSX = "xlsx"
    PDF_TEXT = "pdf_text"
    PDF_TABLE = "pdf_table"
    UNKNOWN = "unknown"


class PriceDocumentInputKind(StrEnum):
    TABLE = "table"
    STRUCTURED_TEXT = "structured_text"
    UNSTRUCTURED_TEXT = "unstructured_text"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class PriceDocumentStatus(StrEnum):
    DRAFT = "draft"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    FAILED = "failed"


class PriceFactStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class PriceValueKind(StrEnum):
    EXACT = "exact"
    STARTING_FROM = "starting_from"
    RANGE = "range"
    ON_REQUEST = "on_request"
    UNKNOWN = "unknown"


class PriceLookupDecision(StrEnum):
    ANSWERABLE = "answerable"
    NEEDS_CLARIFICATION = "needs_clarification"
    REQUIRES_MANAGER = "requires_manager"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNSAFE = "unsafe"


@dataclass(frozen=True, slots=True)
class PriceDocument:
    id: str
    project_id: str
    knowledge_document_id: str
    source_format: PriceDocumentSourceFormat = PriceDocumentSourceFormat.UNKNOWN
    input_kind: PriceDocumentInputKind = PriceDocumentInputKind.UNKNOWN
    status: PriceDocumentStatus = PriceDocumentStatus.DRAFT
    detected_currency: str | None = None
    detected_locale: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("price document id must not be empty")
        if not self.project_id.strip():
            raise ValueError("price document project_id must not be empty")
        if not self.knowledge_document_id.strip():
            raise ValueError("price document knowledge_document_id must not be empty")
        if self.detected_currency is not None and not self.detected_currency.strip():
            raise ValueError("price document detected_currency must not be blank")


@dataclass(frozen=True, slots=True)
class PriceSourceUnit:
    id: str
    price_document_id: str
    source_index: int
    kind: PriceDocumentInputKind
    raw_text: str
    title: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("price source unit id must not be empty")
        if not self.price_document_id.strip():
            raise ValueError("price source unit price_document_id must not be empty")
        if self.source_index < 0:
            raise ValueError("price source unit source_index must be non-negative")
        if not self.raw_text.strip():
            raise ValueError("price source unit raw_text must not be empty")


@dataclass(frozen=True, slots=True)
class PriceSourceRow:
    id: str
    source_unit_id: str
    row_index: int
    raw_cells: Mapping[str, object]
    normalized_cells: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("price source row id must not be empty")
        if not self.source_unit_id.strip():
            raise ValueError("price source row source_unit_id must not be empty")
        if self.row_index < 0:
            raise ValueError("price source row row_index must be non-negative")
        if not self.raw_cells:
            raise ValueError("price source row raw_cells must not be empty")


@dataclass(frozen=True, slots=True)
class PriceRange:
    min_amount: MoneyAmount
    max_amount: MoneyAmount

    def __post_init__(self) -> None:
        if self.min_amount.currency != self.max_amount.currency:
            raise ValueError("price range currency must be consistent")
        if self.min_amount.amount > self.max_amount.amount:
            raise ValueError("price range min_amount must not exceed max_amount")


@dataclass(frozen=True, slots=True)
class PriceCondition:
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("price condition text must not be empty")


@dataclass(frozen=True, slots=True)
class PriceSourceRef:
    price_document_id: str
    source_unit_id: str
    source_row_id: str | None = None
    quote: str = ""

    def __post_init__(self) -> None:
        if not self.price_document_id.strip():
            raise ValueError("price source ref price_document_id must not be empty")
        if not self.source_unit_id.strip():
            raise ValueError("price source ref source_unit_id must not be empty")
        if self.source_row_id is not None and not self.source_row_id.strip():
            raise ValueError("price source ref source_row_id must not be blank")
        if not self.quote.strip():
            raise ValueError("price source ref quote must not be empty")


@dataclass(frozen=True, slots=True)
class PublishedPriceFact:
    id: str
    project_id: str
    price_document_id: str
    item_name: str
    value_kind: PriceValueKind
    unit: str
    status: PriceFactStatus = PriceFactStatus.DRAFT
    amount: MoneyAmount | None = None
    price_range: PriceRange | None = None
    price_text: str = ""
    variant: Mapping[str, str] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    conditions: tuple[PriceCondition, ...] = ()
    source_refs: tuple[PriceSourceRef, ...] = ()
    confidence: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("price fact id must not be empty")
        if not self.project_id.strip():
            raise ValueError("price fact project_id must not be empty")
        if not self.price_document_id.strip():
            raise ValueError("price fact price_document_id must not be empty")
        if not self.item_name.strip():
            raise ValueError("price fact item_name must not be empty")
        if not self.unit.strip():
            raise ValueError("price fact unit must not be empty")
        if not self.source_refs:
            raise ValueError("price fact must be grounded in source refs")
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("price fact confidence must be between 0 and 1")

        if self.value_kind in {PriceValueKind.EXACT, PriceValueKind.STARTING_FROM}:
            if self.amount is None:
                raise ValueError("numeric price fact requires amount")
            if not self.amount.currency.strip():
                raise ValueError("numeric price fact requires currency")
            if self.price_range is not None:
                raise ValueError(
                    "exact/starting_from price fact must not include price_range"
                )
        elif self.value_kind == PriceValueKind.RANGE:
            if self.price_range is None:
                raise ValueError("range price fact requires price_range")
            if self.amount is not None:
                raise ValueError("range price fact must not include amount")
        elif self.value_kind == PriceValueKind.ON_REQUEST:
            if self.amount is not None or self.price_range is not None:
                raise ValueError("on_request price fact must not include numeric price")
            if not self.price_text.strip():
                raise ValueError("on_request price fact requires price_text")
        else:
            raise ValueError("price fact value_kind must be explicit")

    @property
    def normalized_item_name(self) -> str:
        return normalize_slot_value(self.item_name)

    @property
    def normalized_variant(self) -> Mapping[str, str]:
        return {
            normalize_slot_name(key): normalize_slot_value(value)
            for key, value in self.variant.items()
            if normalize_slot_name(key) and normalize_slot_value(value)
        }

    @property
    def is_runtime_eligible(self) -> bool:
        return self.status == PriceFactStatus.PUBLISHED

    def matches_item(self, query_item_name: str) -> bool:
        normalized_query = normalize_slot_value(query_item_name)
        if not normalized_query:
            return False
        if normalized_query == self.normalized_item_name:
            return True
        return normalized_query in {
            normalize_slot_value(alias) for alias in self.aliases
        }

    def matches_variant(self, filters: Mapping[str, str]) -> bool:
        normalized_variant = self.normalized_variant
        for raw_key, raw_value in filters.items():
            key = normalize_slot_name(raw_key)
            value = normalize_slot_value(raw_value)
            if not key or not value:
                continue
            if normalized_variant.get(key) != value:
                return False
        return True


@dataclass(frozen=True, slots=True)
class PriceLookupQuery:
    project_id: str
    item_name: str
    variant_filters: Mapping[str, str] = field(default_factory=dict)
    quantity: int | None = None
    customer_id: str | None = None

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("price lookup project_id must not be empty")
        if not self.item_name.strip():
            raise ValueError("price lookup item_name must not be empty")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("price lookup quantity must be positive")


@dataclass(frozen=True, slots=True)
class PriceLookupResult:
    decision: PriceLookupDecision
    query: PriceLookupQuery
    facts: tuple[PublishedPriceFact, ...] = ()
    missing_slots: tuple[str, ...] = ()
    conflict_reason: str = ""
    manager_reason: str = ""

    def __post_init__(self) -> None:
        if self.decision == PriceLookupDecision.ANSWERABLE:
            if len(self.facts) != 1:
                raise ValueError("answerable price lookup requires exactly one fact")
            if not self.facts[0].is_runtime_eligible:
                raise ValueError("answerable price lookup requires published fact")
        if (
            self.decision == PriceLookupDecision.NEEDS_CLARIFICATION
            and not self.missing_slots
        ):
            raise ValueError("clarification price lookup requires missing_slots")
        if (
            self.decision == PriceLookupDecision.CONFLICT
            and not self.conflict_reason.strip()
        ):
            raise ValueError("conflict price lookup requires conflict_reason")
        if (
            self.decision == PriceLookupDecision.REQUIRES_MANAGER
            and not self.manager_reason.strip()
        ):
            raise ValueError("manager price lookup requires manager_reason")


def runtime_eligible_price_facts(
    facts: Sequence[PublishedPriceFact],
) -> tuple[PublishedPriceFact, ...]:
    return tuple(fact for fact in facts if fact.is_runtime_eligible)


def lookup_price_fact(
    *,
    query: PriceLookupQuery,
    facts: Sequence[PublishedPriceFact],
    required_variant_slots: Sequence[str] = (),
) -> PriceLookupResult:
    eligible = tuple(
        fact
        for fact in runtime_eligible_price_facts(facts)
        if fact.project_id == query.project_id and fact.matches_item(query.item_name)
    )

    if not eligible:
        return PriceLookupResult(decision=PriceLookupDecision.NOT_FOUND, query=query)

    normalized_filters = {
        normalize_slot_name(key): normalize_slot_value(value)
        for key, value in query.variant_filters.items()
        if normalize_slot_name(key) and normalize_slot_value(value)
    }
    missing_slots = tuple(
        slot
        for slot in (normalize_slot_name(item) for item in required_variant_slots)
        if slot and slot not in normalized_filters
    )
    if missing_slots:
        return PriceLookupResult(
            decision=PriceLookupDecision.NEEDS_CLARIFICATION,
            query=query,
            facts=eligible,
            missing_slots=missing_slots,
        )

    matching = tuple(
        fact for fact in eligible if fact.matches_variant(query.variant_filters)
    )
    if not matching:
        return PriceLookupResult(decision=PriceLookupDecision.NOT_FOUND, query=query)

    if len(matching) > 1:
        return PriceLookupResult(
            decision=PriceLookupDecision.CONFLICT,
            query=query,
            facts=matching,
            conflict_reason="multiple_published_price_facts_match_query",
        )

    fact = matching[0]
    if fact.value_kind == PriceValueKind.ON_REQUEST:
        return PriceLookupResult(
            decision=PriceLookupDecision.REQUIRES_MANAGER,
            query=query,
            facts=(fact,),
            manager_reason="price_available_on_request",
        )

    return PriceLookupResult(
        decision=PriceLookupDecision.ANSWERABLE,
        query=query,
        facts=(fact,),
    )
