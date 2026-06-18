from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from src.contexts.llm_runtime.application.policies.llm_route_candidate_builder import (
    LlmRouteAvailability,
)
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute


@dataclass(frozen=True, slots=True)
class LlmEstimatedTokenNeed:
    input_tokens: int
    reserved_output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0:
            raise ValueError("input_tokens must be >= 0")
        if self.reserved_output_tokens < 0:
            raise ValueError("reserved_output_tokens must be >= 0")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.reserved_output_tokens


@dataclass(frozen=True, slots=True)
class LlmQuotaSnapshot:
    """Current provider-neutral quota snapshot for one route."""

    remaining_requests_minute: int | None = None
    remaining_requests_day: int | None = None
    remaining_tokens_minute: int | None = None
    remaining_tokens_day: int | None = None
    remaining_input_tokens_minute: int | None = None
    remaining_output_tokens_minute: int | None = None
    minute_reset_at: datetime | None = None
    daily_reset_at: datetime | None = None
    unavailable_until: datetime | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("remaining_requests_minute", self.remaining_requests_minute),
            ("remaining_requests_day", self.remaining_requests_day),
            ("remaining_tokens_minute", self.remaining_tokens_minute),
            ("remaining_tokens_day", self.remaining_tokens_day),
            ("remaining_input_tokens_minute", self.remaining_input_tokens_minute),
            ("remaining_output_tokens_minute", self.remaining_output_tokens_minute),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be >= 0 when provided")

        for field_name, timestamp in (
            ("minute_reset_at", self.minute_reset_at),
            ("daily_reset_at", self.daily_reset_at),
            ("unavailable_until", self.unavailable_until),
        ):
            if timestamp is None:
                continue
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class LlmQuotaAvailabilityPolicy:
    """Build route availability from quota snapshots and estimated token need."""

    snapshots_by_route: Mapping[LlmRoute, LlmQuotaSnapshot]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "snapshots_by_route",
            MappingProxyType(dict(self.snapshots_by_route)),
        )

    def build_availability_by_route(
        self,
        *,
        routes: tuple[LlmRoute, ...],
        estimated_need: LlmEstimatedTokenNeed,
    ) -> Mapping[LlmRoute, LlmRouteAvailability]:
        availability: dict[LlmRoute, LlmRouteAvailability] = {}

        for route in routes:
            snapshot = self.snapshots_by_route.get(route)
            if snapshot is None:
                availability[route] = LlmRouteAvailability()
                continue

            minute_capacity_available = self._minute_capacity_available(
                snapshot=snapshot,
                estimated_need=estimated_need,
            )
            daily_capacity_available = self._daily_capacity_available(
                snapshot=snapshot,
                estimated_need=estimated_need,
            )

            availability[route] = LlmRouteAvailability(
                minute_capacity_available=minute_capacity_available,
                daily_capacity_available=daily_capacity_available,
                unavailable_until=snapshot.unavailable_until,
            )

        return MappingProxyType(availability)

    def _minute_capacity_available(
        self,
        *,
        snapshot: LlmQuotaSnapshot,
        estimated_need: LlmEstimatedTokenNeed,
    ) -> bool:
        if (
            snapshot.remaining_requests_minute is not None
            and snapshot.remaining_requests_minute < 1
        ):
            return False

        if (
            snapshot.remaining_tokens_minute is not None
            and snapshot.remaining_tokens_minute < estimated_need.input_tokens
        ):
            return False

        if (
            snapshot.remaining_input_tokens_minute is not None
            and snapshot.remaining_input_tokens_minute < estimated_need.input_tokens
        ):
            return False

        if (
            snapshot.remaining_output_tokens_minute is not None
            and snapshot.remaining_output_tokens_minute
            < estimated_need.reserved_output_tokens
        ):
            return False

        return True

    def _daily_capacity_available(
        self,
        *,
        snapshot: LlmQuotaSnapshot,
        estimated_need: LlmEstimatedTokenNeed,
    ) -> bool:
        if (
            snapshot.remaining_requests_day is not None
            and snapshot.remaining_requests_day < 1
        ):
            return False

        if (
            snapshot.remaining_tokens_day is not None
            and snapshot.remaining_tokens_day < estimated_need.total_tokens
        ):
            return False

        return True
