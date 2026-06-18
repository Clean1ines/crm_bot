from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.contexts.llm_runtime.application.ports.llm_provider_port import (
    LlmProviderFailure,
    LlmProviderSuccess,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_response_mapper import (
    GroqProviderHttpResponse,
    GroqProviderResponseMapper,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def test_success_response_extracts_chat_content_usage_and_quota_snapshot() -> None:
    mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=200,
            headers={
                "x-ratelimit-remaining-requests": "14370",
                "x-ratelimit-remaining-tokens": "17997",
            },
            body={
                "choices": [
                    {
                        "message": {
                            "content": '{"ok": true}',
                        },
                    },
                ],
                "usage": {
                    "prompt_tokens": 18,
                    "completion_tokens": 556,
                },
            },
        ),
        observed_at=_now(),
    )

    assert isinstance(mapped.provider_result, LlmProviderSuccess)
    assert mapped.provider_result.raw_text == '{"ok": true}'
    assert mapped.provider_result.usage == TokenUsage(
        input_tokens=18, output_tokens=556
    )
    assert mapped.quota_snapshot.remaining_requests_day == 14370
    assert mapped.quota_snapshot.remaining_tokens_minute == 17997


def test_success_response_tolerates_missing_content_and_usage() -> None:
    mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=200,
            headers={},
            body={},
        ),
        observed_at=_now(),
    )

    assert isinstance(mapped.provider_result, LlmProviderSuccess)
    assert mapped.provider_result.raw_text == ""
    assert mapped.provider_result.usage is None


def test_success_response_supports_responses_api_usage_fields() -> None:
    mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=200,
            headers={
                "x-ratelimit-reset-tokens": "35s",
                "x-ratelimit-reset-requests": "6h12m",
            },
            body={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "input_tokens": 21,
                    "output_tokens": 34,
                },
            },
        ),
        observed_at=_now(),
    )

    assert isinstance(mapped.provider_result, LlmProviderSuccess)
    assert mapped.provider_result.usage == TokenUsage(
        input_tokens=21,
        output_tokens=34,
    )
    assert mapped.quota_snapshot.minute_reset_at == _now() + timedelta(seconds=35)
    assert mapped.quota_snapshot.daily_reset_at == _now() + timedelta(
        hours=6,
        minutes=12,
    )


def test_429_defaults_to_minute_limit_and_uses_retry_after() -> None:
    mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=429,
            headers={"retry-after": "2"},
            body={"error": {"message": "Rate limit reached"}},
        ),
        observed_at=_now(),
    )

    assert isinstance(mapped.provider_result, LlmProviderFailure)
    assert mapped.provider_result.error_kind is LlmErrorKind.MINUTE_LIMIT
    assert mapped.provider_result.wait_until == _now() + timedelta(seconds=2)


def test_429_daily_message_maps_to_daily_limit() -> None:
    mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=429,
            headers={},
            body={"error": {"message": "RPD limit reached for this organization"}},
        ),
        observed_at=_now(),
    )

    assert isinstance(mapped.provider_result, LlmProviderFailure)
    assert mapped.provider_result.error_kind is LlmErrorKind.DAILY_LIMIT


def test_auth_status_codes_map_to_auth_error() -> None:
    for status_code in (401, 403):
        mapped = GroqProviderResponseMapper().map_response(
            response=GroqProviderHttpResponse(
                status_code=status_code,
                headers={},
                body={"error": {"message": "Unauthorized"}},
            ),
            observed_at=_now(),
        )

        assert isinstance(mapped.provider_result, LlmProviderFailure)
        assert mapped.provider_result.error_kind is LlmErrorKind.AUTH_ERROR


def test_request_too_large_status_and_context_message_are_classified() -> None:
    status_mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=413,
            headers={},
            body={"error": {"message": "Payload too large"}},
        ),
        observed_at=_now(),
    )

    assert isinstance(status_mapped.provider_result, LlmProviderFailure)
    assert status_mapped.provider_result.error_kind is LlmErrorKind.REQUEST_TOO_LARGE

    context_mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=400,
            headers={},
            body={"error": {"message": "maximum context length exceeded"}},
        ),
        observed_at=_now(),
    )

    assert isinstance(context_mapped.provider_result, LlmProviderFailure)
    assert context_mapped.provider_result.error_kind is LlmErrorKind.REQUEST_TOO_LARGE


def test_output_too_large_message_is_classified() -> None:
    mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=400,
            headers={},
            body={"error": {"message": "max_completion_tokens exceeded"}},
        ),
        observed_at=_now(),
    )

    assert isinstance(mapped.provider_result, LlmProviderFailure)
    assert mapped.provider_result.error_kind is LlmErrorKind.OUTPUT_TOO_LARGE


def test_server_errors_map_to_network_error() -> None:
    mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=503,
            headers={},
            body={"error": {"message": "Service unavailable"}},
        ),
        observed_at=_now(),
    )

    assert isinstance(mapped.provider_result, LlmProviderFailure)
    assert mapped.provider_result.error_kind is LlmErrorKind.NETWORK_ERROR


def test_unknown_errors_map_to_unknown() -> None:
    mapped = GroqProviderResponseMapper().map_response(
        response=GroqProviderHttpResponse(
            status_code=418,
            headers={},
            body={"error": {"message": "teapot"}},
        ),
        observed_at=_now(),
    )

    assert isinstance(mapped.provider_result, LlmProviderFailure)
    assert mapped.provider_result.error_kind is LlmErrorKind.UNKNOWN
