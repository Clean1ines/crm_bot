from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)


def _payload() -> dict[str, object]:
    return {
        "provider": "groq",
        "account_ref": "groq_org_primary",
        "model_ref": "qwen/qwen3-32b",
        "remaining_minute_requests": 10,
        "remaining_minute_tokens": 1000,
        "remaining_daily_requests": 100,
        "remaining_daily_tokens": 10000,
        "minute_reset_at": None,
        "daily_reset_at": None,
        "actual_input_tokens": 123,
        "actual_output_tokens": 45,
        "actual_total_tokens": 168,
        "outcome_class": "COMPLETED",
        "observed_at": datetime(2026, 6, 24, 12, 0, tzinfo=UTC),
    }


def test_reads_target_actual_input_output_tokens_and_dual_writes_payload() -> None:
    observation = LlmAttemptCapacityObservation.from_payload(_payload())

    assert observation.actual_input_tokens == 123
    assert observation.actual_output_tokens == 45
    assert observation.actual_prompt_tokens == 123
    assert observation.actual_completion_tokens == 45
    assert observation.actual_total_tokens == 168

    event_payload = observation.to_event_payload()

    assert event_payload["actual_input_tokens"] == 123
    assert event_payload["actual_output_tokens"] == 45
    assert event_payload["actual_prompt_tokens"] == 123
    assert event_payload["actual_completion_tokens"] == 45
    assert event_payload["actual_total_tokens"] == 168


def test_reads_legacy_actual_prompt_completion_tokens_as_fallback() -> None:
    payload = _payload()
    del payload["actual_input_tokens"]
    del payload["actual_output_tokens"]
    payload["actual_prompt_tokens"] = 111
    payload["actual_completion_tokens"] = 22

    observation = LlmAttemptCapacityObservation.from_payload(payload)

    assert observation.actual_input_tokens == 111
    assert observation.actual_output_tokens == 22
    assert observation.actual_prompt_tokens == 111
    assert observation.actual_completion_tokens == 22


def test_target_actual_token_keys_take_precedence_over_legacy_keys() -> None:
    payload = _payload()
    payload["actual_prompt_tokens"] = 999
    payload["actual_completion_tokens"] = 888

    observation = LlmAttemptCapacityObservation.from_payload(payload)

    assert observation.actual_input_tokens == 123
    assert observation.actual_output_tokens == 45
    assert observation.actual_prompt_tokens == 123
    assert observation.actual_completion_tokens == 45


@pytest.mark.parametrize(
    "key",
    ("actual_input_tokens", "actual_output_tokens"),
)
def test_rejects_negative_target_actual_token_values(key: str) -> None:
    payload = _payload()
    payload[key] = -1

    with pytest.raises(ValueError, match=key):
        LlmAttemptCapacityObservation.from_payload(payload)
