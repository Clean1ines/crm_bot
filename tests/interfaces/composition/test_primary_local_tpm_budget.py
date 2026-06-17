from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.interfaces.composition import prepare_llm_dispatch_batch


def _now() -> datetime:
    return datetime(2026, 6, 17, 7, 30, tzinfo=timezone.utc)


def _seed_capacity(account_ref: str) -> LlmProviderAccountCapacity:
    return LlmProviderAccountCapacity(
        provider="groq",
        account_ref=account_ref,
        model_ref="qwen/qwen3-32b",
        remaining_minute_requests=60,
        remaining_minute_tokens=6_000,
        remaining_daily_requests=1_000,
        remaining_daily_tokens=500_000,
    )


def _observation(
    *,
    account_ref: str,
    actual_total_tokens: int | None,
) -> LlmAttemptCapacityObservation:
    return LlmAttemptCapacityObservation(
        provider="groq",
        account_ref=account_ref,
        model_ref="qwen/qwen3-32b",
        remaining_minute_requests=None,
        remaining_minute_tokens=None,
        remaining_daily_requests=999,
        remaining_daily_tokens=490_000,
        minute_reset_at=None,
        daily_reset_at=None,
        actual_prompt_tokens=None,
        actual_completion_tokens=None,
        actual_total_tokens=actual_total_tokens,
        outcome_class="succeeded",
        observed_at=_now(),
    )


def test_local_primary_tpm_budget_subtracts_actual_usage_per_account_model_pair() -> (
    None
):
    capacities = prepare_llm_dispatch_batch._local_primary_tpm_account_capacities(
        seed_capacities=(
            _seed_capacity("groq_org_primary"),
            _seed_capacity("groq_org_secondary"),
        ),
        observations=(
            _observation(account_ref="groq_org_primary", actual_total_tokens=4_200),
            _observation(account_ref="groq_org_secondary", actual_total_tokens=1_000),
            _observation(account_ref="groq_org_primary", actual_total_tokens=500),
        ),
    )

    by_account = {capacity.account_ref: capacity for capacity in capacities}

    assert by_account["groq_org_primary"].remaining_minute_tokens == 1_300
    assert by_account["groq_org_primary"].remaining_minute_requests == 58
    assert by_account["groq_org_secondary"].remaining_minute_tokens == 5_000
    assert by_account["groq_org_secondary"].remaining_minute_requests == 59


def test_local_primary_tpm_budget_never_waits_for_provider_reset_headers() -> None:
    capacities = prepare_llm_dispatch_batch._local_primary_tpm_account_capacities(
        seed_capacities=(_seed_capacity("groq_org_primary"),),
        observations=(
            LlmAttemptCapacityObservation(
                provider="groq",
                account_ref="groq_org_primary",
                model_ref="qwen/qwen3-32b",
                remaining_minute_requests=None,
                remaining_minute_tokens=None,
                remaining_daily_requests=999,
                remaining_daily_tokens=490_000,
                minute_reset_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                daily_reset_at=None,
                actual_prompt_tokens=2_000,
                actual_completion_tokens=1_000,
                actual_total_tokens=None,
                outcome_class="succeeded",
                observed_at=_now(),
            ),
        ),
    )

    assert capacities[0].remaining_minute_tokens == 3_000
    assert capacities[0].remaining_minute_requests == 59
