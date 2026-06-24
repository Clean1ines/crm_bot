from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.contexts.llm_runtime.application.policies.llm_quota_availability_policy import (
    LlmEstimatedTokenNeed,
    LlmQuotaSnapshot,
)
from src.contexts.llm_runtime.application.policies.llm_route_candidate_preparation_policy import (
    LlmRouteCandidatePreparationPolicy,
    PrepareLlmRouteCandidatesCommand,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.model_lifecycle import ModelLifecycle
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.rate_limit_profile import (
    RateLimitProfile,
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
    model: str,
    model_rank: int,
    provider: str = "provider",
) -> ModelProfile:
    return ModelProfile(
        provider_id=_provider_id(provider),
        model_id=ModelId(model),
        lifecycle=ModelLifecycle.PRODUCTION,
        context_window_tokens=131_072,
        max_output_tokens=65_536,
        model_rank=model_rank,
        rate_limits=RateLimitProfile(
            requests_per_minute=30,
            requests_per_day=1_000,
            tokens_per_minute=8_000,
            tokens_per_day=200_000,
        ),
        token_price=TokenPrice.unknown(),
        reasoning_profile=ReasoningProfile.unsupported(),
    )


def _account(
    *,
    account: str,
    account_rank: int,
    provider: str = "provider",
) -> ProviderAccount:
    return ProviderAccount(
        provider_id=_provider_id(provider),
        account_ref=ProviderAccountRef(account),
        account_rank=account_rank,
    )


def _route(
    *,
    model: str,
    account: str,
    provider: str = "provider",
) -> LlmRoute:
    return LlmRoute(
        provider_id=_provider_id(provider),
        model_id=ModelId(model),
        account_ref=ProviderAccountRef(account),
    )


def test_preparation_builds_candidates_with_quota_availability_applied() -> None:
    limited_route = _route(model="model-1", account="account-1")
    wait_until = _now() + timedelta(seconds=60)

    candidates = LlmRouteCandidatePreparationPolicy().prepare(
        PrepareLlmRouteCandidatesCommand(
            models=(
                _model(model="model-1", model_rank=0),
                _model(model="model-2", model_rank=1),
            ),
            accounts=(
                _account(account="account-1", account_rank=0),
                _account(account="account-2", account_rank=1),
            ),
            estimated_need=LlmEstimatedTokenNeed(
                input_tokens=1_000,
                estimated_output_tokens=2_000,
            ),
            quota_snapshots_by_route={
                limited_route: LlmQuotaSnapshot(
                    remaining_requests_minute=0,
                    remaining_requests_day=100,
                    unavailable_until=wait_until,
                ),
            },
        ),
    )

    limited_candidate = next(
        candidate for candidate in candidates if candidate.route == limited_route
    )

    assert len(candidates) == 4
    assert not limited_candidate.minute_capacity_available
    assert limited_candidate.daily_capacity_available
    assert limited_candidate.unavailable_until == wait_until


def test_preparation_marks_daily_capacity_unavailable_from_snapshot() -> None:
    daily_limited_route = _route(model="model-1", account="account-1")

    candidates = LlmRouteCandidatePreparationPolicy().prepare(
        PrepareLlmRouteCandidatesCommand(
            models=(_model(model="model-1", model_rank=0),),
            accounts=(_account(account="account-1", account_rank=0),),
            estimated_need=LlmEstimatedTokenNeed(
                input_tokens=1_000,
                estimated_output_tokens=2_000,
            ),
            quota_snapshots_by_route={
                daily_limited_route: LlmQuotaSnapshot(
                    remaining_requests_day=0,
                ),
            },
        ),
    )

    assert len(candidates) == 1
    assert candidates[0].route == daily_limited_route
    assert candidates[0].minute_capacity_available
    assert not candidates[0].daily_capacity_available


def test_preparation_preserves_candidate_order_from_builder() -> None:
    candidates = LlmRouteCandidatePreparationPolicy().prepare(
        PrepareLlmRouteCandidatesCommand(
            models=(
                _model(model="model-rank-1", model_rank=1),
                _model(model="model-rank-0", model_rank=0),
            ),
            accounts=(
                _account(account="account-rank-1", account_rank=1),
                _account(account="account-rank-0", account_rank=0),
            ),
            estimated_need=LlmEstimatedTokenNeed(
                input_tokens=1,
                estimated_output_tokens=1,
            ),
            quota_snapshots_by_route={},
        ),
    )

    assert [
        (candidate.model_rank, candidate.account_rank) for candidate in candidates
    ] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    ]
