from __future__ import annotations

import pytest

from src.contexts.llm_runtime.application.policies.request_output_cap_policy import (
    ProviderOutputCapProfile,
    RequestOutputCapPolicy,
)


def _policy() -> RequestOutputCapPolicy:
    return RequestOutputCapPolicy(
        provider_profile=ProviderOutputCapProfile(
            provider_default_output_cap_tokens=2048,
            request_safety_gap_tokens=300,
        ),
    )


def test_implicit_provider_default_cap_is_effective_when_no_explicit_cap_fits() -> None:
    decision = _policy().decide(
        estimated_input_tokens=5000,
        estimated_output_tokens=1000,
        tokens_remaining=7048,
        hard_output_limit_tokens=8192,
    )

    assert decision.request_output_cap_tokens is None
    assert decision.effective_output_cap_tokens == 2048
    assert decision.reserved_total_tokens == 7048


def test_explicit_request_output_cap_is_calculated_with_safety_gap() -> None:
    decision = _policy().decide(
        estimated_input_tokens=5000,
        estimated_output_tokens=1000,
        tokens_remaining=7348,
        hard_output_limit_tokens=8192,
    )

    assert decision.request_output_cap_tokens == 2048
    assert decision.effective_output_cap_tokens == 2048
    assert decision.reserved_total_tokens == 7048


def test_explicit_request_output_cap_is_clamped_by_model_hard_output_limit() -> None:
    decision = _policy().decide(
        estimated_input_tokens=5000,
        estimated_output_tokens=1000,
        tokens_remaining=20_000,
        hard_output_limit_tokens=4096,
    )

    assert decision.request_output_cap_tokens == 4096
    assert decision.effective_output_cap_tokens == 4096
    assert decision.reserved_total_tokens == 9096


def test_positive_request_cap_below_default_keeps_provider_default_effective_cap() -> (
    None
):
    decision = _policy().decide(
        estimated_input_tokens=5000,
        estimated_output_tokens=1000,
        tokens_remaining=7047,
        hard_output_limit_tokens=8192,
    )

    assert decision.request_output_cap_tokens is None
    assert decision.effective_output_cap_tokens == 2048
    assert decision.reserved_total_tokens == 7048


def test_policy_rejects_provider_default_above_model_hard_output_limit() -> None:
    with pytest.raises(ValueError, match="provider_default_output_cap_tokens"):
        _policy().decide(
            estimated_input_tokens=5000,
            estimated_output_tokens=1000,
            tokens_remaining=7048,
            hard_output_limit_tokens=1024,
        )
