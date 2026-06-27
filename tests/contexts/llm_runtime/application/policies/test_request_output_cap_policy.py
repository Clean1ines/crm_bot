from __future__ import annotations

import pytest

from src.contexts.llm_runtime.application.policies.request_output_cap_policy import (
    ProviderOutputCapProfile,
    RequestOutputCapPolicy,
)


def _policy() -> RequestOutputCapPolicy:
    return RequestOutputCapPolicy(
        provider_profile=ProviderOutputCapProfile(
            provider_default_completion_tokens=2048,
            completion_safety_gap_tokens=300,
        ),
    )


def test_max_completion_tokens_is_omitted_when_remaining_is_not_above_default() -> None:
    decision = _policy().decide(
        input_tokens=5000,
        artifact_tokens=1000,
        tokens_remaining=7048,
        model_max_output_tokens=8192,
    )

    assert decision.input_tokens == 5000
    assert decision.artifact_tokens == 1000
    assert decision.remaining_after_input_tokens == 1748
    assert decision.max_completion_tokens is None
    assert decision.required_window_tokens == 6300


def test_max_completion_tokens_is_calculated_from_remaining_after_input() -> None:
    decision = _policy().decide(
        input_tokens=5000,
        artifact_tokens=1000,
        tokens_remaining=7349,
        model_max_output_tokens=8192,
    )

    assert decision.remaining_after_input_tokens == 2049
    assert decision.max_completion_tokens == 2049
    assert decision.required_window_tokens == 6300


def test_max_completion_tokens_is_clamped_by_model_output_limit() -> None:
    decision = _policy().decide(
        input_tokens=5000,
        artifact_tokens=1000,
        tokens_remaining=20_000,
        model_max_output_tokens=4096,
    )

    assert decision.remaining_after_input_tokens == 14_700
    assert decision.max_completion_tokens == 4096
    assert decision.required_window_tokens == 6300


def test_default_boundary_is_not_enough_to_send_explicit_max_completion_tokens() -> (
    None
):
    decision = _policy().decide(
        input_tokens=5000,
        artifact_tokens=1000,
        tokens_remaining=7348,
        model_max_output_tokens=8192,
    )

    assert decision.remaining_after_input_tokens == 2048
    assert decision.max_completion_tokens is None
    assert decision.required_window_tokens == 6300


def test_negative_remaining_after_input_is_reported_without_explicit_completion_cap() -> (
    None
):
    decision = _policy().decide(
        input_tokens=5000,
        artifact_tokens=1000,
        tokens_remaining=4000,
        model_max_output_tokens=8192,
    )

    assert decision.remaining_after_input_tokens == -1300
    assert decision.max_completion_tokens is None


def test_policy_rejects_provider_default_above_model_output_limit() -> None:
    with pytest.raises(ValueError, match="provider_default_completion_tokens"):
        _policy().decide(
            input_tokens=5000,
            artifact_tokens=1000,
            tokens_remaining=7048,
            model_max_output_tokens=1024,
        )
