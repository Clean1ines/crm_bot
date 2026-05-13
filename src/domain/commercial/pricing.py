from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class MoneyAmount:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not self.currency.strip():
            raise ValueError("currency must not be empty")

    @classmethod
    def from_text(
        cls, amount: str | int | float | Decimal, currency: str
    ) -> "MoneyAmount":
        return cls(amount=Decimal(str(amount)), currency=currency.strip().upper())


@dataclass(frozen=True, slots=True)
class VariantAxis:
    name: str
    required: bool = True
    allowed_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.normalized_name:
            raise ValueError("variant axis name must not be empty")

    @property
    def normalized_name(self) -> str:
        return normalize_slot_name(self.name)


@dataclass(frozen=True, slots=True)
class PricePoint:
    amount: MoneyAmount
    unit: str
    variant: Mapping[str, str] = field(default_factory=dict)
    conditions: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.unit.strip():
            raise ValueError("price unit must not be empty")
        if not self.source_refs:
            raise ValueError("price point must be grounded in source refs")

    @property
    def normalized_variant(self) -> Mapping[str, str]:
        return {
            normalize_slot_name(key): normalize_slot_value(value)
            for key, value in self.variant.items()
            if normalize_slot_name(key) and normalize_slot_value(value)
        }

    def matches(self, filters: Mapping[str, str]) -> bool:
        point_variant = self.normalized_variant
        for raw_key, raw_value in filters.items():
            key = normalize_slot_name(raw_key)
            value = normalize_slot_value(raw_value)
            if not key or not value:
                continue
            if point_variant.get(key) != value:
                return False
        return True


@dataclass(frozen=True, slots=True)
class PriceFact:
    item_name: str
    price_point: PricePoint
    source_document_id: str | None = None
    source_table_id: str | None = None
    source_row_index: int | None = None

    def __post_init__(self) -> None:
        if not self.item_name.strip():
            raise ValueError("price fact item_name must not be empty")


@dataclass(frozen=True, slots=True)
class OfferGroup:
    item_name: str
    price_points: tuple[PricePoint, ...]
    variant_axes: tuple[VariantAxis, ...] = ()
    category: str | None = None

    def __post_init__(self) -> None:
        if not self.item_name.strip():
            raise ValueError("offer group item_name must not be empty")
        if not self.price_points:
            raise ValueError("offer group must contain at least one price point")

    @classmethod
    def from_price_points(
        cls,
        *,
        item_name: str,
        price_points: Sequence[PricePoint],
        variant_axes: Sequence[VariantAxis] = (),
        category: str | None = None,
    ) -> "OfferGroup":
        return cls(
            item_name=item_name,
            price_points=tuple(price_points),
            variant_axes=tuple(variant_axes),
            category=category,
        )

    def required_slots(self, filters: Mapping[str, str]) -> tuple[str, ...]:
        normalized_filters = {
            normalize_slot_name(key)
            for key, value in filters.items()
            if normalize_slot_name(key) and normalize_slot_value(value)
        }
        missing: list[str] = []
        for axis in self.variant_axes:
            if not axis.required:
                continue
            axis_name = axis.normalized_name
            if axis_name and axis_name not in normalized_filters:
                missing.append(axis_name)
        return tuple(missing)

    def matching_price_points(
        self, filters: Mapping[str, str]
    ) -> tuple[PricePoint, ...]:
        return tuple(point for point in self.price_points if point.matches(filters))

    def needs_disambiguation(self, filters: Mapping[str, str]) -> bool:
        if self.required_slots(filters):
            return True
        return len(self.matching_price_points(filters)) > 1


def normalize_slot_name(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def normalize_slot_value(value: str) -> str:
    return " ".join(value.strip().lower().split())
