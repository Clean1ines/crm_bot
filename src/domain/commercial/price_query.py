from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from src.domain.commercial.pricing import OfferGroup


class PriceQueryIntent(StrEnum):
    DIRECT_LOOKUP = "direct_lookup"
    VARIANT_LOOKUP = "variant_lookup"
    RANGE_LOOKUP = "range_lookup"
    COMPARISON = "comparison"
    TOTAL_CALCULATION = "total_calculation"
    CONDITION_QUERY = "condition_query"
    AVAILABILITY_QUERY = "availability_query"
    LIVE_CRM_LOOKUP = "live_crm_lookup"
    PERSONAL_QUOTE = "personal_quote"
    DISAMBIGUATION_REQUIRED = "disambiguation_required"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class PriceQuery:
    intent: PriceQueryIntent
    item_name: str | None = None
    variant_filters: Mapping[str, str] = field(default_factory=dict)
    quantity: int | None = None
    customer_id: str | None = None
    comparison_targets: tuple[str, ...] = ()

    @property
    def requires_live_operational_source(self) -> bool:
        return self.intent in {
            PriceQueryIntent.LIVE_CRM_LOOKUP,
            PriceQueryIntent.PERSONAL_QUOTE,
            PriceQueryIntent.AVAILABILITY_QUERY,
        }

    def missing_slots_for_offer(self, offer: OfferGroup) -> tuple[str, ...]:
        return offer.required_slots(self.variant_filters)

    def with_intent(self, intent: PriceQueryIntent) -> "PriceQuery":
        return PriceQuery(
            intent=intent,
            item_name=self.item_name,
            variant_filters=dict(self.variant_filters),
            quantity=self.quantity,
            customer_id=self.customer_id,
            comparison_targets=self.comparison_targets,
        )


@dataclass(frozen=True, slots=True)
class PriceQueryResolution:
    query: PriceQuery
    missing_slots: tuple[str, ...] = ()
    matched_offer_name: str | None = None

    @property
    def is_answerable(self) -> bool:
        return (
            not self.missing_slots and self.query.intent != PriceQueryIntent.NOT_FOUND
        )

    @property
    def needs_clarification(self) -> bool:
        return bool(self.missing_slots) or (
            self.query.intent == PriceQueryIntent.DISAMBIGUATION_REQUIRED
        )
