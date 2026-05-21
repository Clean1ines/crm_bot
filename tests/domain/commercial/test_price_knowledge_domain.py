from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentInputKind,
    PriceFactStatus,
    PriceLookupDecision,
    PriceLookupQuery,
    PriceRange,
    PriceSourceRef,
    PriceValueKind,
    PublishedPriceFact,
    lookup_price_fact,
)
from src.domain.commercial.pricing import MoneyAmount


def _source_ref() -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id="price-doc-1",
        source_unit_id="source-unit-1",
        quote="Тариф Pro стоит 2490 ₽/мес.",
    )


def _fact(
    *,
    fact_id: str = "fact-1",
    item_name: str = "Pro",
    status: PriceFactStatus = PriceFactStatus.PUBLISHED,
    amount: MoneyAmount | None = None,
    value_kind: PriceValueKind = PriceValueKind.EXACT,
    unit: str = "month",
    variant: dict[str, str] | None = None,
    price_text: str = "",
) -> PublishedPriceFact:
    default_amount = (
        None
        if value_kind == PriceValueKind.ON_REQUEST
        else amount or MoneyAmount.from_text("2490", "RUB")
    )

    return PublishedPriceFact(
        id=fact_id,
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name=item_name,
        value_kind=value_kind,
        status=status,
        amount=default_amount,
        unit=unit,
        variant=variant or {},
        price_text=price_text,
        source_refs=(_source_ref(),),
        confidence=Decimal("0.9"),
    )


def test_price_document_requires_knowledge_document_link() -> None:
    with pytest.raises(ValueError, match="knowledge_document_id"):
        PriceDocument(
            id="price-doc-1",
            project_id="project-1",
            knowledge_document_id="",
            input_kind=PriceDocumentInputKind.TABLE,
        )


def test_published_price_fact_must_be_grounded_in_source_refs() -> None:
    with pytest.raises(ValueError, match="source refs"):
        PublishedPriceFact(
            id="fact-1",
            project_id="project-1",
            price_document_id="price-doc-1",
            item_name="Pro",
            value_kind=PriceValueKind.EXACT,
            amount=MoneyAmount.from_text("2490", "RUB"),
            unit="month",
            status=PriceFactStatus.PUBLISHED,
            source_refs=(),
        )


def test_numeric_price_fact_requires_amount_and_currency() -> None:
    with pytest.raises(ValueError, match="requires amount"):
        PublishedPriceFact(
            id="fact-1",
            project_id="project-1",
            price_document_id="price-doc-1",
            item_name="Pro",
            value_kind=PriceValueKind.EXACT,
            unit="month",
            status=PriceFactStatus.PUBLISHED,
            source_refs=(_source_ref(),),
        )


def test_range_price_fact_requires_consistent_range() -> None:
    fact = PublishedPriceFact(
        id="fact-1",
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name="Consulting",
        value_kind=PriceValueKind.RANGE,
        price_range=PriceRange(
            min_amount=MoneyAmount.from_text("5000", "RUB"),
            max_amount=MoneyAmount.from_text("15000", "RUB"),
        ),
        unit="project",
        status=PriceFactStatus.PUBLISHED,
        source_refs=(_source_ref(),),
    )

    assert fact.is_runtime_eligible is True


def test_on_request_price_fact_requires_text_and_routes_to_manager() -> None:
    fact = _fact(
        value_kind=PriceValueKind.ON_REQUEST,
        amount=None,
        price_text="Цена рассчитывается индивидуально.",
    )
    query = PriceLookupQuery(project_id="project-1", item_name="Pro")

    result = lookup_price_fact(query=query, facts=(fact,))

    assert result.decision == PriceLookupDecision.REQUIRES_MANAGER
    assert result.manager_reason == "price_available_on_request"


def test_runtime_lookup_ignores_non_published_price_facts() -> None:
    query = PriceLookupQuery(project_id="project-1", item_name="Pro")
    draft_fact = _fact(status=PriceFactStatus.DRAFT)

    result = lookup_price_fact(query=query, facts=(draft_fact,))

    assert result.decision == PriceLookupDecision.NOT_FOUND


def test_runtime_lookup_returns_exact_published_fact() -> None:
    query = PriceLookupQuery(project_id="project-1", item_name="Pro")
    fact = _fact()

    result = lookup_price_fact(query=query, facts=(fact,))

    assert result.decision == PriceLookupDecision.ANSWERABLE
    assert result.facts == (fact,)


def test_runtime_lookup_uses_aliases_and_variant_filters() -> None:
    fact = PublishedPriceFact(
        id="fact-1",
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name="Тариф Pro",
        aliases=("pro", "про"),
        value_kind=PriceValueKind.EXACT,
        amount=MoneyAmount.from_text("2490", "RUB"),
        unit="month",
        variant={"Period": "Monthly"},
        status=PriceFactStatus.PUBLISHED,
        source_refs=(_source_ref(),),
    )
    query = PriceLookupQuery(
        project_id="project-1",
        item_name="pro",
        variant_filters={"period": "monthly"},
    )

    result = lookup_price_fact(query=query, facts=(fact,))

    assert result.decision == PriceLookupDecision.ANSWERABLE


def test_runtime_lookup_requires_missing_variant_slots_before_matching() -> None:
    fact = _fact(variant={"period": "monthly"})
    query = PriceLookupQuery(project_id="project-1", item_name="Pro")

    result = lookup_price_fact(
        query=query,
        facts=(fact,),
        required_variant_slots=("period",),
    )

    assert result.decision == PriceLookupDecision.NEEDS_CLARIFICATION
    assert result.missing_slots == ("period",)


def test_runtime_lookup_reports_conflict_for_multiple_matching_published_facts() -> (
    None
):
    query = PriceLookupQuery(project_id="project-1", item_name="Pro")
    left = _fact(fact_id="fact-1")
    right = _fact(fact_id="fact-2", amount=MoneyAmount.from_text("2990", "RUB"))

    result = lookup_price_fact(query=query, facts=(left, right))

    assert result.decision == PriceLookupDecision.CONFLICT
    assert result.conflict_reason == "multiple_published_price_facts_match_query"
