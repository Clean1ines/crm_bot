from __future__ import annotations

from decimal import Decimal

import pytest

from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
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


def _provider_id() -> ProviderId:
    return ProviderId("provider")


def _model_profile(
    *,
    reasoning_profile: ReasoningProfile | None = None,
    context_window_tokens: int = 131_072,
    max_output_tokens: int = 65_536,
) -> ModelProfile:
    return ModelProfile(
        provider_id=_provider_id(),
        model_id=ModelId("model-1"),
        lifecycle=ModelLifecycle.PRODUCTION,
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        model_rank=0,
        rate_limits=RateLimitProfile(
            requests_per_minute=30,
            requests_per_day=1_000,
            tokens_per_minute=8_000,
            tokens_per_day=200_000,
        ),
        token_price=TokenPrice(
            input_per_million=Decimal("0.10"),
            output_per_million=Decimal("0.20"),
        ),
        reasoning_profile=reasoning_profile or ReasoningProfile.unsupported(),
    )


def test_model_profile_keeps_capacity_pricing_limits_and_reasoning_capability() -> None:
    profile = _model_profile(
        reasoning_profile=ReasoningProfile(
            supported_efforts=(
                ReasoningEffort.NONE,
                ReasoningEffort.DEFAULT,
            ),
            default_effort=ReasoningEffort.NONE,
        ),
    )

    assert profile.context_window_tokens == 131_072
    assert profile.max_output_tokens == 65_536
    assert profile.rate_limits.requests_per_minute == 30
    assert profile.rate_limits.tokens_per_day == 200_000
    assert profile.token_price.input_per_million == Decimal("0.10")
    assert profile.can_disable_reasoning


def test_reasoning_profile_can_represent_models_without_reasoning_controls() -> None:
    profile = ReasoningProfile.unsupported()

    assert not profile.supports_reasoning_control
    assert not profile.can_disable_reasoning
    assert profile.default_effort is None


def test_reasoning_profile_validates_default_effort() -> None:
    with pytest.raises(ValueError):
        ReasoningProfile(
            supported_efforts=(ReasoningEffort.LOW,),
            default_effort=ReasoningEffort.NONE,
        )

    with pytest.raises(ValueError):
        ReasoningProfile(
            supported_efforts=(ReasoningEffort.NONE, ReasoningEffort.NONE),
        )


def test_model_profile_rejects_invalid_capacity_and_rank() -> None:
    with pytest.raises(ValueError):
        _model_profile(
            context_window_tokens=8_000,
            max_output_tokens=16_000,
        )

    with pytest.raises(ValueError):
        ModelProfile(
            provider_id=_provider_id(),
            model_id=ModelId("model-1"),
            lifecycle=ModelLifecycle.PRODUCTION,
            context_window_tokens=8_000,
            max_output_tokens=4_000,
            model_rank=-1,
            rate_limits=RateLimitProfile(),
            token_price=TokenPrice.unknown(),
            reasoning_profile=ReasoningProfile.unsupported(),
        )


def test_rate_limit_profile_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError):
        RateLimitProfile(requests_per_minute=0)

    with pytest.raises(ValueError):
        RateLimitProfile(tokens_per_day=-1)


def test_token_price_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        TokenPrice(input_per_million=Decimal("-0.01"))

    with pytest.raises(ValueError):
        TokenPrice(output_per_million=Decimal("-0.01"))


def test_provider_account_status_and_rank() -> None:
    enabled = ProviderAccount(
        provider_id=_provider_id(),
        account_ref=ProviderAccountRef("account-1"),
        account_rank=0,
    )

    assert enabled.enabled

    disabled = ProviderAccount(
        provider_id=_provider_id(),
        account_ref=ProviderAccountRef("account-1"),
        account_rank=0,
        status=ProviderAccountStatus.DISABLED,
    )

    assert not disabled.enabled

    with pytest.raises(ValueError):
        ProviderAccount(
            provider_id=_provider_id(),
            account_ref=ProviderAccountRef("account-1"),
            account_rank=-1,
        )
