from __future__ import annotations

from decimal import Decimal

from src.domain.commercial.price_knowledge import (
    PriceCondition,
    PriceDocument,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceDocumentStatus,
    PriceFactStatus,
    PriceRange,
    PriceSourceRef,
    PriceSourceRow,
    PriceSourceUnit,
    PriceValueKind,
    PublishedPriceFact,
)
from src.domain.commercial.pricing import MoneyAmount
from src.infrastructure.db.repositories.commercial_price_mappers import (
    jsonb_array_payload,
    jsonb_object_payload,
    price_document_from_row,
    price_fact_aliases_payload,
    price_fact_amount,
    price_fact_currency,
    price_fact_from_row,
    price_fact_max_amount,
    price_fact_min_amount,
    price_fact_variant_payload,
    price_source_refs_payload,
    price_source_row_from_row,
    price_source_unit_from_row,
)


def _source_ref() -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id="price-doc-1",
        source_unit_id="unit-1",
        source_row_id="row-1",
        quote="Pro — 2490 ₽/мес.",
    )


def test_price_document_from_row_maps_storage_to_domain() -> None:
    document = price_document_from_row(
        {
            "id": "price-doc-1",
            "project_id": "project-1",
            "knowledge_document_id": "knowledge-doc-1",
            "source_format": "csv",
            "input_kind": "table",
            "status": "ready",
            "detected_currency": "RUB",
            "detected_locale": "ru",
        }
    )

    assert document == PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
        status=PriceDocumentStatus.READY,
        detected_currency="RUB",
        detected_locale="ru",
    )


def test_price_source_unit_and_row_from_rows_map_jsonb_payloads() -> None:
    unit = price_source_unit_from_row(
        {
            "id": "unit-1",
            "price_document_id": "price-doc-1",
            "source_index": 0,
            "kind": "table",
            "raw_text": "Тариф,Цена",
            "title": "Прайс",
            "metadata": {"sheet": "main"},
        }
    )
    row = price_source_row_from_row(
        {
            "id": "row-1",
            "source_unit_id": "unit-1",
            "row_index": 2,
            "raw_cells": {"A": "Pro", "B": "2490"},
            "normalized_cells": {"name": "Pro", "price": "2490"},
        }
    )

    assert unit == PriceSourceUnit(
        id="unit-1",
        price_document_id="price-doc-1",
        source_index=0,
        kind=PriceDocumentInputKind.TABLE,
        raw_text="Тариф,Цена",
        title="Прайс",
        metadata={"sheet": "main"},
    )
    assert row == PriceSourceRow(
        id="row-1",
        source_unit_id="unit-1",
        row_index=2,
        raw_cells={"A": "Pro", "B": "2490"},
        normalized_cells={"name": "Pro", "price": "2490"},
    )


def test_exact_price_fact_payloads_and_row_roundtrip() -> None:
    fact = PublishedPriceFact(
        id="fact-1",
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name="Тариф Pro",
        value_kind=PriceValueKind.EXACT,
        status=PriceFactStatus.PUBLISHED,
        amount=MoneyAmount.from_text("2490", "rub"),
        unit="month",
        price_text="2490 ₽/мес.",
        variant={"Period": "Monthly"},
        aliases=("pro", "про"),
        conditions=(PriceCondition("для новых клиентов"),),
        source_refs=(_source_ref(),),
        confidence=Decimal("0.95"),
    )

    row_fact = price_fact_from_row(
        {
            "id": fact.id,
            "project_id": fact.project_id,
            "price_document_id": fact.price_document_id,
            "item_name": fact.item_name,
            "value_kind": fact.value_kind.value,
            "status": fact.status.value,
            "amount": price_fact_amount(fact),
            "min_amount": price_fact_min_amount(fact),
            "max_amount": price_fact_max_amount(fact),
            "currency": price_fact_currency(fact),
            "unit": fact.unit,
            "price_text": fact.price_text,
            "variant": price_fact_variant_payload(fact),
            "aliases": price_fact_aliases_payload(fact),
            "conditions": ["для новых клиентов"],
            "source_refs": price_source_refs_payload(fact.source_refs),
            "confidence": Decimal("0.95"),
        }
    )

    assert row_fact.value_kind == PriceValueKind.EXACT
    assert row_fact.amount == MoneyAmount.from_text("2490", "RUB")
    assert row_fact.price_range is None
    assert row_fact.normalized_variant == {"period": "monthly"}
    assert row_fact.source_refs == fact.source_refs


def test_range_and_on_request_price_facts_roundtrip_shapes() -> None:
    range_fact = price_fact_from_row(
        {
            "id": "fact-range",
            "project_id": "project-1",
            "price_document_id": "price-doc-1",
            "item_name": "Консалтинг",
            "value_kind": "range",
            "status": "published",
            "amount": None,
            "min_amount": Decimal("5000"),
            "max_amount": Decimal("15000"),
            "currency": "RUB",
            "unit": "project",
            "price_text": "",
            "variant": {},
            "aliases": [],
            "conditions": [],
            "source_refs": price_source_refs_payload((_source_ref(),)),
            "confidence": Decimal("0.8"),
        }
    )
    on_request_fact = price_fact_from_row(
        {
            "id": "fact-custom",
            "project_id": "project-1",
            "price_document_id": "price-doc-1",
            "item_name": "Enterprise",
            "value_kind": "on_request",
            "status": "published",
            "amount": None,
            "min_amount": None,
            "max_amount": None,
            "currency": None,
            "unit": "contract",
            "price_text": "Цена рассчитывается индивидуально.",
            "variant": {},
            "aliases": [],
            "conditions": [],
            "source_refs": price_source_refs_payload((_source_ref(),)),
            "confidence": Decimal("0.7"),
        }
    )

    assert range_fact.price_range == PriceRange(
        min_amount=MoneyAmount.from_text("5000", "RUB"),
        max_amount=MoneyAmount.from_text("15000", "RUB"),
    )
    assert range_fact.amount is None
    assert on_request_fact.amount is None
    assert on_request_fact.price_range is None
    assert on_request_fact.price_text == "Цена рассчитывается индивидуально."


def test_jsonb_payload_helpers_preserve_objects_and_arrays() -> None:
    assert jsonb_object_payload({"ключ": "значение"}) == '{"ключ": "значение"}'
    assert jsonb_array_payload(["a", "b"]) == '["a", "b"]'
