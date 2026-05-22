from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import cast

import pytest

from src.application.ports.commercial_price import CommercialPriceLookupPort
from src.domain.commercial.price_knowledge import (
    PriceFactStatus,
    PriceLookupQuery,
    PriceSourceRef,
    PriceValueKind,
    PublishedPriceFact,
)
from src.domain.commercial.pricing import MoneyAmount
from src.tools.builtins import CommercialPriceLookupTool
from src.tools.registry import ToolExecutionError


def _source_ref() -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id="price-doc-1",
        source_unit_id="unit-1",
        source_row_id="row-1",
        quote="Pro — 2490 ₽/мес.",
    )


def _fact(
    *,
    fact_id: str = "fact-1",
    item_name: str = "Pro",
    value_kind: PriceValueKind = PriceValueKind.EXACT,
    price_text: str = "",
) -> PublishedPriceFact:
    amount = (
        None
        if value_kind == PriceValueKind.ON_REQUEST
        else MoneyAmount.from_text("2490", "RUB")
    )
    return PublishedPriceFact(
        id=fact_id,
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name=item_name,
        value_kind=value_kind,
        status=PriceFactStatus.PUBLISHED,
        amount=amount,
        price_text=price_text,
        unit="month",
        aliases=("pro",),
        source_refs=(_source_ref(),),
        confidence=Decimal("0.91"),
    )


class FakeCommercialPriceLookupRepo:
    def __init__(
        self,
        *,
        facts: Sequence[PublishedPriceFact],
        required_slots: Sequence[str] = (),
    ) -> None:
        self.facts = tuple(facts)
        self.required_slots = tuple(required_slots)
        self.seen_queries: list[PriceLookupQuery] = []
        self.seen_limits: list[int] = []

    async def list_published_price_facts_for_lookup(
        self,
        *,
        query: PriceLookupQuery,
        limit: int = 20,
    ) -> tuple[PublishedPriceFact, ...]:
        self.seen_queries.append(query)
        self.seen_limits.append(limit)
        return self.facts

    async def list_required_variant_slots(
        self,
        *,
        project_id: str,
        item_name: str,
    ) -> tuple[str, ...]:
        return self.required_slots


@pytest.mark.asyncio
async def test_commercial_price_lookup_tool_returns_answerable_fact() -> None:
    repo = FakeCommercialPriceLookupRepo(facts=(_fact(),))
    tool = CommercialPriceLookupTool(cast(CommercialPriceLookupPort, repo))

    payload = await tool.run(
        {"item_name": "pro", "limit": 5},
        {"project_id": "project-1", "thread_id": "thread-1"},
    )

    assert payload["decision"] == "answerable"
    assert payload["candidate_count"] == 1
    assert repo.seen_limits == [5]

    facts = payload["facts"]
    assert isinstance(facts, list)
    first_fact = facts[0]
    assert isinstance(first_fact, dict)
    assert first_fact["item_name"] == "Pro"
    assert first_fact["amount"] == {"amount": "2490", "currency": "RUB"}


@pytest.mark.asyncio
async def test_commercial_price_lookup_tool_returns_clarification_for_missing_slot() -> (
    None
):
    repo = FakeCommercialPriceLookupRepo(
        facts=(_fact(),),
        required_slots=("period",),
    )
    tool = CommercialPriceLookupTool(cast(CommercialPriceLookupPort, repo))

    payload = await tool.run(
        {"item_name": "Pro"},
        {"project_id": "project-1"},
    )

    assert payload["decision"] == "needs_clarification"
    assert payload["missing_slots"] == ["period"]


@pytest.mark.asyncio
async def test_commercial_price_lookup_tool_routes_on_request_to_manager() -> None:
    repo = FakeCommercialPriceLookupRepo(
        facts=(
            _fact(
                value_kind=PriceValueKind.ON_REQUEST,
                price_text="Цена рассчитывается индивидуально.",
            ),
        ),
    )
    tool = CommercialPriceLookupTool(cast(CommercialPriceLookupPort, repo))

    payload = await tool.run(
        {"item_name": "Pro"},
        {"project_id": "project-1"},
    )

    assert payload["decision"] == "requires_manager"
    assert payload["manager_reason"] == "price_available_on_request"


@pytest.mark.asyncio
async def test_commercial_price_lookup_tool_rejects_empty_item_name() -> None:
    repo = FakeCommercialPriceLookupRepo(facts=())
    tool = CommercialPriceLookupTool(cast(CommercialPriceLookupPort, repo))

    with pytest.raises(ToolExecutionError, match="item_name"):
        await tool.run({"item_name": "   "}, {"project_id": "project-1"})
