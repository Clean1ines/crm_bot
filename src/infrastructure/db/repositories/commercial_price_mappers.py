from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
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


def jsonb_object_payload(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, default=str)


def jsonb_array_payload(values: Sequence[object]) -> str:
    return json.dumps(list(values), ensure_ascii=False, default=str)


def price_source_ref_payload(source_ref: PriceSourceRef) -> dict[str, object]:
    return {
        "price_document_id": source_ref.price_document_id,
        "source_unit_id": source_ref.source_unit_id,
        "source_row_id": source_ref.source_row_id,
        "quote": source_ref.quote,
    }


def price_source_refs_payload(
    source_refs: Sequence[PriceSourceRef],
) -> list[dict[str, object]]:
    return [price_source_ref_payload(source_ref) for source_ref in source_refs]


def price_conditions_payload(conditions: Sequence[PriceCondition]) -> list[str]:
    return [condition.text for condition in conditions]


def price_fact_variant_payload(fact: PublishedPriceFact) -> dict[str, str]:
    return dict(fact.normalized_variant)


def price_fact_aliases_payload(fact: PublishedPriceFact) -> list[str]:
    return [alias.strip() for alias in fact.aliases if alias.strip()]


def price_fact_amount(fact: PublishedPriceFact) -> Decimal | None:
    return fact.amount.amount if fact.amount is not None else None


def price_fact_min_amount(fact: PublishedPriceFact) -> Decimal | None:
    return fact.price_range.min_amount.amount if fact.price_range is not None else None


def price_fact_max_amount(fact: PublishedPriceFact) -> Decimal | None:
    return fact.price_range.max_amount.amount if fact.price_range is not None else None


def price_fact_currency(fact: PublishedPriceFact) -> str | None:
    if fact.amount is not None:
        return fact.amount.currency
    if fact.price_range is not None:
        return fact.price_range.min_amount.currency
    return None


def price_document_from_row(row: Mapping[str, object]) -> PriceDocument:
    return PriceDocument(
        id=_text(row.get("id")),
        project_id=_text(row.get("project_id")),
        knowledge_document_id=_text(row.get("knowledge_document_id")),
        source_format=PriceDocumentSourceFormat(
            _text(row.get("source_format"), "unknown")
        ),
        input_kind=PriceDocumentInputKind(_text(row.get("input_kind"), "unknown")),
        status=PriceDocumentStatus(_text(row.get("status"), "draft")),
        detected_currency=_optional_text(row.get("detected_currency")),
        detected_locale=_optional_text(row.get("detected_locale")),
    )


def price_source_unit_from_row(row: Mapping[str, object]) -> PriceSourceUnit:
    return PriceSourceUnit(
        id=_text(row.get("id")),
        price_document_id=_text(row.get("price_document_id")),
        source_index=_int(row.get("source_index")),
        kind=PriceDocumentInputKind(_text(row.get("kind"), "unknown")),
        raw_text=_text(row.get("raw_text")),
        title=_text(row.get("title")),
        metadata=_json_object(row.get("metadata")),
    )


def price_source_row_from_row(row: Mapping[str, object]) -> PriceSourceRow:
    return PriceSourceRow(
        id=_text(row.get("id")),
        source_unit_id=_text(row.get("source_unit_id")),
        row_index=_int(row.get("row_index")),
        raw_cells=_json_object(row.get("raw_cells")),
        normalized_cells=_json_text_mapping(row.get("normalized_cells")),
    )


def price_fact_from_row(row: Mapping[str, object]) -> PublishedPriceFact:
    value_kind = PriceValueKind(_text(row.get("value_kind")))
    currency = _optional_text(row.get("currency"))
    amount_value = _decimal_or_none(row.get("amount"))
    min_amount_value = _decimal_or_none(row.get("min_amount"))
    max_amount_value = _decimal_or_none(row.get("max_amount"))

    amount = (
        MoneyAmount(amount=amount_value, currency=currency)
        if amount_value is not None and currency is not None
        else None
    )
    price_range = (
        PriceRange(
            min_amount=MoneyAmount(amount=min_amount_value, currency=currency),
            max_amount=MoneyAmount(amount=max_amount_value, currency=currency),
        )
        if min_amount_value is not None
        and max_amount_value is not None
        and currency is not None
        else None
    )

    return PublishedPriceFact(
        id=_text(row.get("id")),
        project_id=_text(row.get("project_id")),
        price_document_id=_text(row.get("price_document_id")),
        item_name=_text(row.get("item_name")),
        value_kind=value_kind,
        unit=_text(row.get("unit")),
        status=PriceFactStatus(_text(row.get("status"), "draft")),
        amount=amount,
        price_range=price_range,
        price_text=_text(row.get("price_text")),
        variant=_json_text_mapping(row.get("variant")),
        aliases=_text_tuple(row.get("aliases")),
        conditions=_price_conditions(row.get("conditions")),
        source_refs=_price_source_refs(row.get("source_refs")),
        confidence=_decimal(row.get("confidence")),
    )


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str | bytes | bytearray):
        return int(value)
    raise TypeError(f"expected integer-compatible value, got {type(value).__name__}")


def _decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(loaded, Mapping):
            return {str(key): item for key, item in loaded.items()}
    return {}


def _json_text_mapping(value: object) -> dict[str, str]:
    payload = _json_object(value)
    return {
        str(key): str(item)
        for key, item in payload.items()
        if str(key).strip() and str(item).strip()
    }


def _json_array(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return ()
        if isinstance(loaded, list):
            return tuple(loaded)
    return ()


def _text_tuple(value: object) -> tuple[str, ...]:
    return tuple(
        text for text in (str(item).strip() for item in _json_array(value)) if text
    )


def _price_conditions(value: object) -> tuple[PriceCondition, ...]:
    return tuple(PriceCondition(text=text) for text in _text_tuple(value))


def _price_source_refs(value: object) -> tuple[PriceSourceRef, ...]:
    refs: list[PriceSourceRef] = []
    for item in _json_array(value):
        if not isinstance(item, Mapping):
            continue
        refs.append(
            PriceSourceRef(
                price_document_id=_text(item.get("price_document_id")),
                source_unit_id=_text(item.get("source_unit_id")),
                source_row_id=_optional_text(item.get("source_row_id")),
                quote=_text(item.get("quote")),
            )
        )
    return tuple(refs)
