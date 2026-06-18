from __future__ import annotations

from decimal import Decimal

import pytest

from src.contexts.llm_runtime.domain.value_objects.model_lifecycle import ModelLifecycle
from src.contexts.llm_runtime.domain.value_objects.reasoning_effort import (
    ReasoningEffort,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GROQ_PROVIDER_ID,
    GroqAccountSeed,
    build_groq_free_plan_model_profiles,
    build_groq_provider_accounts,
)


def test_groq_free_plan_seed_contains_target_text_models_in_fallback_order() -> None:
    profiles = build_groq_free_plan_model_profiles()

    assert [profile.model_id.value for profile in profiles] == [
        "qwen/qwen3-32b",
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-120b",
    ]
    assert [profile.model_rank for profile in profiles] == [0, 2, 3, 4, 5]
    assert all(profile.provider_id == GROQ_PROVIDER_ID for profile in profiles)


def test_qwen_seed_can_disable_reasoning_for_output_budget_control() -> None:
    qwen = build_groq_free_plan_model_profiles()[0]

    assert qwen.model_id.value == "qwen/qwen3-32b"
    assert qwen.lifecycle is ModelLifecycle.PREVIEW
    assert qwen.reasoning_profile.can_disable_reasoning
    assert qwen.reasoning_profile.default_effort is ReasoningEffort.NONE
    assert qwen.context_window_tokens == 131_072
    assert qwen.max_output_tokens == 40_960
    assert qwen.rate_limits.requests_per_minute == 60
    assert qwen.rate_limits.tokens_per_minute == 6_000
    assert qwen.rate_limits.tokens_per_day == 500_000


def test_llama_instant_seed_uses_free_plan_capacity_and_large_output_window() -> None:
    llama_instant = build_groq_free_plan_model_profiles()[1]

    assert llama_instant.model_id.value == "llama-3.1-8b-instant"
    assert llama_instant.lifecycle is ModelLifecycle.PRODUCTION
    assert llama_instant.context_window_tokens == 131_072
    assert llama_instant.max_output_tokens == 131_072
    assert llama_instant.rate_limits.requests_per_minute == 30
    assert llama_instant.rate_limits.requests_per_day == 14_400
    assert llama_instant.rate_limits.tokens_per_minute == 6_000
    assert llama_instant.rate_limits.tokens_per_day == 500_000
    assert llama_instant.token_price.input_per_million == Decimal("0.05")
    assert llama_instant.token_price.output_per_million == Decimal("0.08")


def test_gpt_oss_120b_seed_represent_reasoning_controls_without_disable_none() -> None:
    profiles = build_groq_free_plan_model_profiles()
    gpt_oss_120b = profiles[4]

    assert gpt_oss_120b.reasoning_profile.supports_reasoning_control
    assert not gpt_oss_120b.reasoning_profile.can_disable_reasoning
    assert gpt_oss_120b.reasoning_profile.default_effort is ReasoningEffort.MEDIUM
    assert gpt_oss_120b.max_output_tokens == 65_536
    assert gpt_oss_120b.rate_limits.requests_per_day == 1_000
    assert gpt_oss_120b.rate_limits.tokens_per_day == 200_000


def test_llama_70b_seed_uses_lower_daily_token_limit_and_32768_output() -> None:
    llama_70b = build_groq_free_plan_model_profiles()[2]

    assert llama_70b.model_id.value == "llama-3.3-70b-versatile"
    assert llama_70b.max_output_tokens == 32_768
    assert llama_70b.rate_limits.tokens_per_minute == 12_000
    assert llama_70b.rate_limits.tokens_per_day == 100_000
    assert not llama_70b.can_disable_reasoning


def test_scout_seed_uses_30000_tpm_limit() -> None:
    scout = build_groq_free_plan_model_profiles()[3]

    assert scout.model_id.value == "meta-llama/llama-4-scout-17b-16e-instruct"
    assert scout.rate_limits.tokens_per_minute == 30_000
    assert scout.rate_limits.tokens_per_day == 500_000


def test_groq_provider_accounts_are_capacity_slots_not_secret_values() -> None:
    accounts = build_groq_provider_accounts(
        (
            GroqAccountSeed(account_ref="groq_org_primary", account_rank=0),
            GroqAccountSeed(account_ref="groq_org_secondary", account_rank=1),
        ),
    )

    assert [account.account_ref.value for account in accounts] == [
        "groq_org_primary",
        "groq_org_secondary",
    ]
    assert [account.account_rank for account in accounts] == [0, 1]
    assert all(account.provider_id == GROQ_PROVIDER_ID for account in accounts)
    assert all(account.enabled for account in accounts)


def test_groq_account_seed_rejects_empty_ref_and_negative_rank() -> None:
    with pytest.raises(ValueError):
        GroqAccountSeed(account_ref="", account_rank=0)

    with pytest.raises(ValueError):
        GroqAccountSeed(account_ref="groq_org_primary", account_rank=-1)
