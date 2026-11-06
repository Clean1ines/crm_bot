from __future__ import annotations

from decimal import Decimal

import pytest

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


def test_groq_free_plan_seed_contains_primary_and_degraded_models() -> None:
    profiles = build_groq_free_plan_model_profiles()

    assert [profile.model_id.value for profile in profiles] == [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]
    assert [profile.model_rank for profile in profiles] == [0, 1]
    assert [profile.enabled for profile in profiles] == [True, False]
    assert all(profile.provider_id == GROQ_PROVIDER_ID for profile in profiles)


def test_model_budget_profile_for_ref_returns_seeded_model_budget_fields() -> None:
    gpt_oss = model_budget_profile_for_ref("openai/gpt-oss-120b")

    assert gpt_oss.rate_limits.tokens_per_minute == 8_000
    assert gpt_oss.model_char_to_token_multiplier == Decimal("3.7")


def test_gpt_oss_120b_seed_represent_reasoning_controls_without_disable_none() -> None:
    profiles = build_groq_free_plan_model_profiles()
    gpt_oss_120b = profiles[0]

    assert gpt_oss_120b.reasoning_profile.supports_reasoning_control
    assert not gpt_oss_120b.reasoning_profile.can_disable_reasoning
    assert gpt_oss_120b.reasoning_profile.default_effort is ReasoningEffort.LOW
    assert gpt_oss_120b.max_output_tokens == 65_536
    assert gpt_oss_120b.rate_limits.requests_per_day == 1_000
    assert gpt_oss_120b.rate_limits.tokens_per_minute == 8_000
    assert gpt_oss_120b.rate_limits.tokens_per_day == 200_000
    assert gpt_oss_120b.model_char_to_token_multiplier == Decimal("3.7")
    assert gpt_oss_120b.supports_json_schema is True


def test_gpt_oss_20b_seed_uses_degraded_capacity_and_schema_support() -> None:
    gpt_oss_20b = build_groq_free_plan_model_profiles()[1]

    assert gpt_oss_20b.model_id.value == "openai/gpt-oss-20b"
    assert gpt_oss_20b.max_output_tokens == 65_536
    assert gpt_oss_20b.rate_limits.tokens_per_minute == 8_000
    assert gpt_oss_20b.rate_limits.tokens_per_day == 200_000
    assert gpt_oss_20b.token_price.input_per_million == Decimal("0.075")
    assert gpt_oss_20b.token_price.output_per_million == Decimal("0.30")
    assert gpt_oss_20b.supports_json_schema is True
    assert gpt_oss_20b.enabled is False


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
