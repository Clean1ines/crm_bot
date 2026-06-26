import pytest

from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


def _profile() -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a",
        input_tokens=3000,
        artifact_tokens=500,
        request_count=1,
    )


def test_max_items_for_uses_min_of_rpm_tpm_rpd_tpd() -> None:
    account = LlmProviderAccountCapacity(
        provider="groq",
        account_ref="org-1",
        model_ref="qwen",
        remaining_minute_requests=10,
        remaining_minute_tokens=9000,
        remaining_daily_requests=100,
        remaining_daily_tokens=50000,
    )

    assert account.max_items_for(_profile()) == 2


def test_zero_daily_requests_returns_zero() -> None:
    account = LlmProviderAccountCapacity(
        provider="groq",
        account_ref="org-1",
        model_ref="qwen",
        remaining_minute_requests=10,
        remaining_minute_tokens=9000,
        remaining_daily_requests=0,
        remaining_daily_tokens=50000,
    )

    assert account.max_items_for(_profile()) == 0


def test_zero_minute_tokens_returns_zero() -> None:
    account = LlmProviderAccountCapacity(
        provider="groq",
        account_ref="org-1",
        model_ref="qwen",
        remaining_minute_requests=10,
        remaining_minute_tokens=0,
        remaining_daily_requests=100,
        remaining_daily_tokens=50000,
    )

    assert account.max_items_for(_profile()) == 0


def test_rejects_empty_provider_account_or_model_refs() -> None:
    with pytest.raises(ValueError, match="provider must be non-empty"):
        LlmProviderAccountCapacity(
            provider=" ",
            account_ref="org-1",
            model_ref="qwen",
            remaining_minute_requests=1,
            remaining_minute_tokens=1,
            remaining_daily_requests=1,
            remaining_daily_tokens=1,
        )

    with pytest.raises(ValueError, match="account_ref must be non-empty"):
        LlmProviderAccountCapacity(
            provider="groq",
            account_ref=" ",
            model_ref="qwen",
            remaining_minute_requests=1,
            remaining_minute_tokens=1,
            remaining_daily_requests=1,
            remaining_daily_tokens=1,
        )

    with pytest.raises(ValueError, match="model_ref must be non-empty"):
        LlmProviderAccountCapacity(
            provider="groq",
            account_ref="org-1",
            model_ref=" ",
            remaining_minute_requests=1,
            remaining_minute_tokens=1,
            remaining_daily_requests=1,
            remaining_daily_tokens=1,
        )


def test_rejects_negative_remaining_values() -> None:
    with pytest.raises(ValueError, match="remaining_minute_requests must be >= 0"):
        LlmProviderAccountCapacity(
            provider="groq",
            account_ref="org-1",
            model_ref="qwen",
            remaining_minute_requests=-1,
            remaining_minute_tokens=1,
            remaining_daily_requests=1,
            remaining_daily_tokens=1,
        )
