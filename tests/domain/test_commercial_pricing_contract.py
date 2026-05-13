from __future__ import annotations

import pytest

from src.domain.commercial.price_query import PriceQuery, PriceQueryIntent
from src.domain.commercial.pricing import (
    MoneyAmount,
    OfferGroup,
    PricePoint,
    VariantAxis,
)


def test_offer_group_requires_variant_slots_for_price_lookup() -> None:
    offer = OfferGroup.from_price_points(
        item_name="Business cards",
        variant_axes=(
            VariantAxis("quantity"),
            VariantAxis("paper"),
        ),
        price_points=(
            PricePoint(
                amount=MoneyAmount.from_text("500", "RUB"),
                unit="order",
                variant={"quantity": "100", "paper": "standard"},
                source_refs=("row:1",),
            ),
            PricePoint(
                amount=MoneyAmount.from_text("1800", "RUB"),
                unit="order",
                variant={"quantity": "500", "paper": "standard"},
                source_refs=("row:2",),
            ),
        ),
    )

    assert offer.required_slots({"quantity": "500"}) == ("paper",)
    assert offer.needs_disambiguation({"quantity": "500"})


def test_offer_group_matches_normalized_variant_filters() -> None:
    offer = OfferGroup.from_price_points(
        item_name="Business cards",
        variant_axes=(VariantAxis("quantity"),),
        price_points=(
            PricePoint(
                amount=MoneyAmount.from_text("1800", "RUB"),
                unit="order",
                variant={"Quantity": "500"},
                source_refs=("row:2",),
            ),
        ),
    )

    matches = offer.matching_price_points({" quantity ": " 500 "})

    assert len(matches) == 1
    assert matches[0].amount.amount == MoneyAmount.from_text("1800", "RUB").amount


def test_price_query_knows_when_live_source_is_required() -> None:
    query = PriceQuery(
        intent=PriceQueryIntent.PERSONAL_QUOTE,
        item_name="installation",
        customer_id="client-1",
    )

    assert query.requires_live_operational_source


def test_price_point_must_be_grounded() -> None:
    with pytest.raises(ValueError, match="source refs"):
        PricePoint(
            amount=MoneyAmount.from_text("100", "RUB"),
            unit="item",
            source_refs=(),
        )
