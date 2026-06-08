from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.contexts.llm_runtime.application.policies.llm_route_candidate_builder import (
    LlmRouteAvailability,
    LlmRouteCandidateBuilder,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.model_lifecycle import ModelLifecycle
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_account_status import (
    ProviderAccountStatus,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.rate_limit_profile import (
    RateLimitProfile,
)
from src.contexts.llm_runtime.domain.value_objects.reasoning_effort import (
    ReasoningEffort,
)
from src.contexts.llm_runtime.domain.value_objects.reasoning_profile import (
    ReasoningProfile,
)
from src.contexts.llm_runtime.domain.value_objects.token_price import TokenPrice


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _provider_id(value: str = "provider") -> ProviderId:
    return ProviderId(value)


def _model(
    *,
    provider: str = "provider",
    model: str = "model-1",
    model_rank: int = 0,
    context_window_tokens: int = 131_072,
    max_output_tokens: int = 65_536,
    enabled: bool = True,
) -> ModelProfile:
    return ModelProfile(
        provider_id=_provider_id(provider),
        model_id=ModelId(model),
        lifecycle=ModelLifecycle.PRODUCTION,
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        model_rank=model_rank,
        rate_limits=RateLimitProfile(
            requests_per_minute=30,
            requests_per_day=1_000,
            tokens_per_minute=8_000,
            tokens_per_day=200_000,
        ),
        token_price=TokenPrice.unknown(),
        reasoning_profile=ReasoningProfile(
            supported_efforts=(ReasoningEffort.NONE, ReasoningEffort.DEFAULT),
            default_effort=ReasoningEffort.NONE,
        ),
        enabled=enabled,
    )


def _account(
    *,
    provider: str = "provider",
    account: str = "account-1",
    account_rank: int = 0,
    enabled: bool = True,
) -> ProviderAccount:
    return ProviderAccount(
        provider_id=_provider_id(provider),
        account_ref=ProviderAccountRef(account),
        account_rank=account_rank,
        status=ProviderAccountStatus.ENABLED
        if enabled
        else ProviderAccountStatus.DISABLED,
    )


def _route(
    *,
    provider: str = "provider",
    model: str = "model-1",
    account: str = "account-1",
) -> LlmRoute:
    return LlmRoute(
        provider_id=_provider_id(provider),
        model_id=ModelId(model),
        account_ref=ProviderAccountRef(account),
    )


def test_builder_creates_cross_product_for_enabled_models_and_accounts_with_same_provider() -> (
    None
):
    candidates = LlmRouteCandidateBuilder().build_candidates(
        models=(
            _model(model="model-1", model_rank=0),
            _model(model="model-2", model_rank=1),
        ),
        accounts=(
            _account(account="account-1", account_rank=0),
            _account(account="account-2", account_rank=1),
        ),
    )

    assert [candidate.route for candidate in candidates] == [
        _route(model="model-1", account="account-1"),
        _route(model="model-1", account="account-2"),
        _route(model="model-2", account="account-1"),
        _route(model="model-2", account="account-2"),
    ]


def test_builder_skips_disabled_models_and_accounts() -> None:
    candidates = LlmRouteCandidateBuilder().build_candidates(
        models=(
            _model(model="enabled-model"),
            _model(model="disabled-model", enabled=False),
        ),
        accounts=(
            _account(account="enabled-account"),
            _account(account="disabled-account", enabled=False),
        ),
    )

    assert len(candidates) == 1
    assert candidates[0].route == _route(
        model="enabled-model", account="enabled-account"
    )


def test_builder_skips_accounts_from_other_providers() -> None:
    candidates = LlmRouteCandidateBuilder().build_candidates(
        models=(_model(provider="provider-a", model="model-a"),),
        accounts=(
            _account(provider="provider-a", account="account-a"),
            _account(provider="provider-b", account="account-b"),
        ),
    )

    assert len(candidates) == 1
    assert candidates[0].route == _route(
        provider="provider-a", model="model-a", account="account-a"
    )


def test_builder_copies_model_capacity_and_account_rank_into_candidates() -> None:
    candidates = LlmRouteCandidateBuilder().build_candidates(
        models=(
            _model(
                model="model-1",
                model_rank=3,
                context_window_tokens=32_000,
                max_output_tokens=8_000,
            ),
        ),
        accounts=(_account(account="account-1", account_rank=2),),
    )

    candidate = candidates[0]

    assert candidate.context_window_tokens == 32_000
    assert candidate.max_output_tokens == 8_000
    assert candidate.model_rank == 3
    assert candidate.account_rank == 2


def test_builder_applies_route_availability_snapshot() -> None:
    route = _route(model="model-1", account="account-1")
    unavailable_until = _now() + timedelta(seconds=60)

    candidates = LlmRouteCandidateBuilder().build_candidates(
        models=(_model(model="model-1"),),
        accounts=(_account(account="account-1"),),
        availability_by_route={
            route: LlmRouteAvailability(
                minute_capacity_available=False,
                daily_capacity_available=True,
                unavailable_until=unavailable_until,
            ),
        },
    )

    candidate = candidates[0]

    assert candidate.route == route
    assert not candidate.minute_capacity_available
    assert candidate.daily_capacity_available
    assert candidate.unavailable_until == unavailable_until


def test_builder_sorts_by_model_rank_then_account_rank() -> None:
    candidates = LlmRouteCandidateBuilder().build_candidates(
        models=(
            _model(model="model-rank-2", model_rank=2),
            _model(model="model-rank-0", model_rank=0),
            _model(model="model-rank-1", model_rank=1),
        ),
        accounts=(
            _account(account="account-rank-2", account_rank=2),
            _account(account="account-rank-0", account_rank=0),
            _account(account="account-rank-1", account_rank=1),
        ),
    )

    assert [
        (candidate.model_rank, candidate.account_rank) for candidate in candidates
    ] == [
        (0, 0),
        (0, 1),
        (0, 2),
        (1, 0),
        (1, 1),
        (1, 2),
        (2, 0),
        (2, 1),
        (2, 2),
    ]


def test_route_availability_requires_timezone_aware_unavailable_until() -> None:
    try:
        LlmRouteAvailability(unavailable_until=datetime(2026, 6, 8, 12, 0))
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
