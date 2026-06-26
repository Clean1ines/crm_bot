from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.application.sagas.llm_provider_message_capacity_estimate import (
    ProviderMessageCapacityEstimate,
    estimate_provider_message_capacity,
)


def test_provider_message_capacity_estimate_uses_estimated_output_tokens() -> None:
    estimate = ProviderMessageCapacityEstimate(
        estimated_input_tokens=100,
        estimated_output_tokens=1024,
        estimated_total_tokens=1124,
    )

    assert estimate.estimated_output_tokens == 1024
    assert estimate.to_payload() == {
        "estimator": "claim_builder_primary_model_char_multiplier_actual_provider_messages",
        "estimated_input_tokens": 100,
        "estimated_output_tokens": 1024,
        "estimated_total_tokens": 1124,
    }


def test_estimate_provider_message_capacity_returns_estimated_output_payload() -> None:
    estimate = estimate_provider_message_capacity(
        provider_messages=(
            {
                "role": "user",
                "content": "x" * 5000,
            },
        ),
    )

    payload = estimate.to_payload()

    assert payload["estimated_input_tokens"] > 0
    assert payload["estimated_output_tokens"] >= 1024
    assert payload["estimated_total_tokens"] == (
        payload["estimated_input_tokens"] + payload["estimated_output_tokens"]
    )
    assert "reserved_output_tokens" not in payload


def test_provider_message_capacity_estimate_rejects_invalid_total() -> None:
    with pytest.raises(ValueError, match="estimated_total_tokens"):
        ProviderMessageCapacityEstimate(
            estimated_input_tokens=100,
            estimated_output_tokens=1024,
            estimated_total_tokens=999,
        )
