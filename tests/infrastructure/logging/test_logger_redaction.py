from __future__ import annotations

import pytest

from src.infrastructure.logging.logger import redact_sensitive_log_values


def test_redaction_keeps_operational_token_counters_visible() -> None:
    event = redact_sensitive_log_values(
        None,
        "info",
        {
            "remaining_minute_tokens": 1234,
            "remaining_daily_tokens": 5678,
            "reserved_tokens": 900,
            "required_window_tokens": 2300,
            "actual_prompt_tokens": 3008,
            "actual_completion_tokens": 4323,
            "actual_total_tokens": 7331,
            "max_completion_tokens": 4323,
        },
    )

    assert event == {
        "remaining_minute_tokens": 1234,
        "remaining_daily_tokens": 5678,
        "reserved_tokens": 900,
        "required_window_tokens": 2300,
        "actual_prompt_tokens": 3008,
        "actual_completion_tokens": 4323,
        "actual_total_tokens": 7331,
        "max_completion_tokens": 4323,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("remaining_tokens", "1234"),
        ("reset_tokens", "2m"),
        ("actual_tokens", 2400),
        ("quota_remaining_minute_tokens", 1234),
        ("quota_remaining_daily_tokens", 190000),
        ("remaining_minute_tokens", 1234),
        ("remaining_daily_tokens", 190000),
        ("reserved_tokens", 3000),
        ("required_window_tokens", 3846),
        ("actual_prompt_tokens", 3008),
        ("actual_completion_tokens", 4323),
        ("actual_total_tokens", 7331),
        ("max_completion_tokens", 4323),
        ("estimated_input_tokens", 3377),
        ("planned_output_tokens", 369),
        ("input_tokens", 3377),
        ("output_tokens", 4323),
        ("total_tokens", 7700),
        ("prompt_tokens", 3008),
        ("completion_tokens", 4323),
        ("artifact_tokens", 369),
        ("safety_gap_tokens", 300),
        ("model_tpm_limit", 8000),
        ("limit_tokens", "8000"),
    ),
)
def test_redaction_preserves_new_operational_token_fields(
    field: str,
    value: object,
) -> None:
    event = redact_sensitive_log_values(None, "info", {field: value})

    assert event[field] == value


@pytest.mark.parametrize(
    "field",
    (
        "api_token",
        "bot_token",
        "github_token",
        "provider_token",
        "service_token",
        "private_token",
        "access_token",
        "refresh_token",
        "auth_token",
        "id_token",
        "csrf_token",
        "session_token",
        "authorization",
        "api_key",
        "user_access_tokens",
        "provider_secret_tokens",
    ),
)
def test_redaction_removes_secret_like_token_fields(field: str) -> None:
    event = redact_sensitive_log_values(None, "info", {field: "secret"})

    assert event[field] == "[REDACTED]"


def test_redaction_removes_secrets_and_authorization_values() -> None:
    event = redact_sensitive_log_values(
        None,
        "info",
        {
            "api_key": "gsk_abcdefghijklmnopqrstuvwxyz123456",
            "api_token": "secret-api-token",
            "bot_token": "secret-bot-token",
            "github_token": "secret-github-token",
            "provider_token": "secret-provider-token",
            "authorization": "Bearer abc.def",
            "access_token": "secret-access-token",
            "nested": {
                "refresh_token": "secret-refresh-token",
                "remaining_minute_tokens": 42,
            },
            "items": [
                {
                    "provider_token": "secret-provider-token",
                    "remaining_tokens": "1234",
                }
            ],
            "message": "using Bearer xyz.secret in text",
        },
    )

    assert event["api_key"] == "[REDACTED]"
    assert event["api_token"] == "[REDACTED]"
    assert event["bot_token"] == "[REDACTED]"
    assert event["github_token"] == "[REDACTED]"
    assert event["provider_token"] == "[REDACTED]"
    assert event["authorization"] == "[REDACTED]"
    assert event["access_token"] == "[REDACTED]"
    assert event["nested"] == {
        "refresh_token": "[REDACTED]",
        "remaining_minute_tokens": 42,
    }
    assert event["items"] == [
        {
            "provider_token": "[REDACTED]",
            "remaining_tokens": "1234",
        }
    ]
    assert event["message"] == "using [REDACTED] in text"


def test_redaction_scrubs_secrets_inside_structured_provider_error_message() -> None:
    event = redact_sensitive_log_values(
        None,
        "warning",
        {
            "event": "llm_groq_provider_error",
            "error_message": (
                "Authorization: Bearer secret-token api_key=gsk_secret_value"
            ),
            "error_type": "invalid_request_error",
            "error_code": "bad_request",
        },
    )

    assert "secret-token" not in str(event)
    assert "gsk_secret_value" not in str(event)
    assert event["error_message"] == "Authorization: [REDACTED] api_key=[REDACTED]"
