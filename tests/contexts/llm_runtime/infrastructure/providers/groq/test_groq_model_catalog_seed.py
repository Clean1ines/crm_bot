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
    model_budget_profile_for_ref,
)


def test_groq_free_plan_seed_contains_target_text_models_in_fallback_order() -> None:
    profiles = build_groq_free_plan_model_profiles()

    assert [profile.model_id.value for profile in profiles] == [
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]
    assert [profile.model_rank for profile in profiles] == [0, 5, 2]
    assert all(profile.provider_id == GROQ_PROVIDER_ID for profile in profiles)


def test_qwen_seed_can_disable_reasoning_for_output_budget_control() -> None:
    profiles = build_groq_free_plan_model_profiles()
    qwen = next(
        profile for profile in profiles if profile.model_id.value == "qwen/qwen3.6-27b"
    )
    assert qwen.model_id.value == "qwen/qwen3.6-27b"
    assert qwen.lifecycle is ModelLifecycle.PREVIEW
    assert qwen.reasoning_profile.can_disable_reasoning
    assert qwen.reasoning_profile.default_effort is ReasoningEffort.NONE
    assert qwen.context_window_tokens == 131_072
    assert qwen.max_output_tokens == 32_768
    assert qwen.rate_limits.requests_per_minute == 30
    assert qwen.rate_limits.tokens_per_minute == 8_000
    assert qwen.rate_limits.tokens_per_day == 200_000
    assert qwen.token_price.input_per_million == Decimal("0.60")
    assert qwen.token_price.output_per_million == Decimal("3.00")
    assert qwen.model_char_to_token_multiplier == Decimal("2.8")


def test_model_budget_profile_for_ref_returns_seeded_model_budget_fields() -> None:
    qwen = model_budget_profile_for_ref("qwen/qwen3.6-27b")
    gpt_oss = model_budget_profile_for_ref("openai/gpt-oss-120b")

    assert qwen.rate_limits.tokens_per_minute == 8_000
    assert qwen.model_char_to_token_multiplier == Decimal("2.8")
    assert gpt_oss.rate_limits.tokens_per_minute == 8_000
    assert gpt_oss.model_char_to_token_multiplier == Decimal("3.7")


def test_gpt_oss_120b_seed_represent_reasoning_controls_without_disable_none() -> None:
    profiles = build_groq_free_plan_model_profiles()
    gpt_oss_120b = profiles[1]

    assert gpt_oss_120b.reasoning_profile.supports_reasoning_control
    assert not gpt_oss_120b.reasoning_profile.can_disable_reasoning
    assert gpt_oss_120b.reasoning_profile.default_effort is ReasoningEffort.MEDIUM
    assert gpt_oss_120b.max_output_tokens == 65_536
    assert gpt_oss_120b.rate_limits.requests_per_day == 1_000
    assert gpt_oss_120b.rate_limits.tokens_per_minute == 8_000
    assert gpt_oss_120b.rate_limits.tokens_per_day == 200_000
    assert gpt_oss_120b.model_char_to_token_multiplier == Decimal("3.7")
    assert gpt_oss_120b.supports_json_schema is False


def test_gpt_oss_20b_seed_uses_degraded_capacity_and_schema_support() -> None:
    gpt_oss_20b = build_groq_free_plan_model_profiles()[2]

    assert gpt_oss_20b.model_id.value == "openai/gpt-oss-20b"
    assert gpt_oss_20b.max_output_tokens == 65_536
    assert gpt_oss_20b.rate_limits.tokens_per_minute == 8_000
    assert gpt_oss_20b.rate_limits.tokens_per_day == 200_000
    assert gpt_oss_20b.token_price.input_per_million == Decimal("0.075")
    assert gpt_oss_20b.token_price.output_per_million == Decimal("0.30")
    assert gpt_oss_20b.supports_json_schema is True


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
