from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from src.contexts.llm_runtime.application.policies.llm_quota_availability_policy import (
    LlmEstimatedTokenNeed,
    LlmQuotaAvailabilityPolicy,
    LlmQuotaSnapshot,
)
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route(model: str = "model-1", account: str = "account-1") -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId(model),
        account_ref=ProviderAccountRef(account),
    )


def _need() -> LlmEstimatedTokenNeed:
    return LlmEstimatedTokenNeed(
        input_tokens=1_000,
        completion_tokens=2_000,
    )


def test_unknown_route_is_available_by_default() -> None:
    route = _route()

    availability = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={},
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert isinstance(availability, MappingProxyType)
    assert availability[route].minute_capacity_available
    assert availability[route].daily_capacity_available
    assert availability[route].unavailable_until is None


def test_minute_request_exhaustion_marks_minute_unavailable() -> None:
    route = _route()
    reset_at = _now() + timedelta(seconds=60)

    availability = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={
            route: LlmQuotaSnapshot(
                remaining_requests_minute=0,
                remaining_requests_day=100,
                unavailable_until=reset_at,
            ),
        },
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert not availability[route].minute_capacity_available
    assert availability[route].daily_capacity_available
    assert availability[route].unavailable_until == reset_at


def test_daily_request_exhaustion_marks_daily_unavailable() -> None:
    route = _route()

    availability = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={
            route: LlmQuotaSnapshot(
                remaining_requests_minute=10,
                remaining_requests_day=0,
            ),
        },
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert availability[route].minute_capacity_available
    assert not availability[route].daily_capacity_available


def test_combined_minute_token_shortage_uses_input_tokens_only() -> None:
    route = _route()

    availability = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={
            route: LlmQuotaSnapshot(
                remaining_tokens_minute=999,
            ),
        },
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert not availability[route].minute_capacity_available
    assert availability[route].daily_capacity_available


def test_combined_daily_token_shortage_marks_daily_unavailable() -> None:
    route = _route()

    availability = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={
            route: LlmQuotaSnapshot(
                remaining_tokens_day=2_999,
            ),
        },
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert availability[route].minute_capacity_available
    assert not availability[route].daily_capacity_available


def test_separate_input_output_minute_limits_are_supported() -> None:
    route = _route()

    input_limited = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={
            route: LlmQuotaSnapshot(
                remaining_input_tokens_minute=999,
                remaining_output_tokens_minute=2_000,
            ),
        },
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert not input_limited[route].minute_capacity_available

    output_limited = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={
            route: LlmQuotaSnapshot(
                remaining_input_tokens_minute=1_000,
                remaining_output_tokens_minute=1_999,
            ),
        },
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert not output_limited[route].minute_capacity_available


def test_sufficient_limits_keep_route_available() -> None:
    route = _route()

    availability = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={
            route: LlmQuotaSnapshot(
                remaining_requests_minute=1,
                remaining_requests_day=1,
                remaining_tokens_minute=3_000,
                remaining_tokens_day=3_000,
                remaining_input_tokens_minute=1_000,
                remaining_output_tokens_minute=2_000,
            ),
        },
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert availability[route].minute_capacity_available
    assert availability[route].daily_capacity_available


def test_combined_minute_token_budget_uses_input_and_completion_tokens() -> None:
    route = _route()

    availability = LlmQuotaAvailabilityPolicy(
        snapshots_by_route={
            route: LlmQuotaSnapshot(
                remaining_tokens_minute=2_999,
            ),
        },
    ).build_availability_by_route(
        routes=(route,),
        estimated_need=_need(),
    )

    assert not availability[route].minute_capacity_available


def test_estimated_token_need_validates_non_negative_values() -> None:
    with pytest.raises(ValueError):
        LlmEstimatedTokenNeed(input_tokens=-1, completion_tokens=0)

    with pytest.raises(ValueError):
        LlmEstimatedTokenNeed(input_tokens=0, completion_tokens=-1)


def test_quota_snapshot_validates_values_and_timestamps() -> None:
    with pytest.raises(ValueError):
        LlmQuotaSnapshot(remaining_requests_minute=-1)

    with pytest.raises(ValueError):
        LlmQuotaSnapshot(unavailable_until=datetime(2026, 6, 8, 12, 0))
