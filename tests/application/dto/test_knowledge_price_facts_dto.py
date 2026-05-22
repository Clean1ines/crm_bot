from __future__ import annotations

from decimal import Decimal

from src.application.dto.knowledge_dto import (
    KnowledgePriceFactsMutationResultDto,
    KnowledgePriceFactsResponseDto,
)
from src.domain.commercial.price_knowledge import (
    PriceFactStatus,
    PriceSourceRef,
    PriceValueKind,
    PublishedPriceFact,
)
from src.domain.commercial.pricing import MoneyAmount


def _fact() -> PublishedPriceFact:
    return PublishedPriceFact(
        id="fact-1",
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name="Pro",
        value_kind=PriceValueKind.EXACT,
        status=PriceFactStatus.NEEDS_REVIEW,
        amount=MoneyAmount.from_text("2490", "RUB"),
        unit="month",
        source_refs=(
            PriceSourceRef(
                price_document_id="price-doc-1",
                source_unit_id="unit-1",
                source_row_id="row-1",
                quote="Pro | 2490 ₽",
            ),
        ),
        confidence=Decimal("0.72"),
    )


def test_price_facts_response_serializes_review_facts_for_frontend() -> None:
    response = KnowledgePriceFactsResponseDto.from_facts(
        knowledge_document_id="knowledge-doc-1",
        price_document_id="price-doc-1",
        facts=(_fact(),),
    )

    payload = response.to_dict()

    assert payload["knowledge_document_id"] == "knowledge-doc-1"
    assert payload["price_document_id"] == "price-doc-1"
    assert payload["is_empty"] is False
    assert payload["items"] == payload["facts"]
    facts = payload["facts"]
    assert isinstance(facts, list)
    assert facts

    first_fact = facts[0]
    assert isinstance(first_fact, dict)
    assert first_fact["status"] == "needs_review"
    assert first_fact["item_name"] == "Pro"
    assert first_fact["amount"] == {"amount": "2490", "currency": "RUB"}

    source_refs = first_fact["source_refs"]
    assert isinstance(source_refs, list)
    assert source_refs

    first_source_ref = source_refs[0]
    assert isinstance(first_source_ref, dict)
    assert first_source_ref["source_row_id"] == "row-1"


def test_price_facts_response_empty_when_document_has_no_price_document() -> None:
    response = KnowledgePriceFactsResponseDto.empty(
        knowledge_document_id="knowledge-doc-1",
    )

    payload = response.to_dict()

    assert payload["price_document_id"] is None
    assert payload["facts"] == []
    assert payload["items"] == []
    assert payload["is_empty"] is True


def test_price_facts_mutation_result_serializes_affected_count() -> None:
    response = KnowledgePriceFactsMutationResultDto.from_facts(
        knowledge_document_id="knowledge-doc-1",
        price_document_id="price-doc-1",
        affected_count=1,
        facts=(_fact(),),
    )

    payload = response.to_dict()

    assert payload["knowledge_document_id"] == "knowledge-doc-1"
    assert payload["price_document_id"] == "price-doc-1"
    assert payload["affected_count"] == 1
    assert payload["items"] == payload["facts"]
