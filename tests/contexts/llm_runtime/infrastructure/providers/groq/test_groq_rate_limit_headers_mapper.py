from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_rate_limit_headers_mapper import (
    GroqRateLimitHeadersMapper,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def test_mapper_reads_remaining_requests_and_tokens_from_groq_headers() -> None:
    snapshot = GroqRateLimitHeadersMapper().map_headers(
        headers={
            "x-ratelimit-remaining-requests": "14370",
            "x-ratelimit-remaining-tokens": "17997",
        },
        observed_at=_now(),
    )

    assert snapshot.remaining_requests_day == 14370
    assert snapshot.remaining_tokens_minute == 17997
    assert snapshot.unavailable_until is None


def test_mapper_is_case_insensitive_for_headers() -> None:
    snapshot = GroqRateLimitHeadersMapper().map_headers(
        headers={
            "X-RateLimit-Remaining-Requests": "10",
            "X-RateLimit-Remaining-Tokens": "20",
        },
        observed_at=_now(),
    )

    assert snapshot.remaining_requests_day == 10
    assert snapshot.remaining_tokens_minute == 20


def test_retry_after_seconds_sets_unavailable_until() -> None:
    snapshot = GroqRateLimitHeadersMapper().map_headers(
        headers={
            "retry-after": "2",
        },
        observed_at=_now(),
    )

    assert snapshot.unavailable_until == _now() + timedelta(seconds=2)


def test_reset_headers_parse_minutes_and_fractional_seconds() -> None:
    snapshot = GroqRateLimitHeadersMapper().map_headers(
        headers={
            "x-ratelimit-reset-requests": "2m59.56s",
            "x-ratelimit-reset-tokens": "7.66s",
        },
        observed_at=_now(),
    )

    assert snapshot.unavailable_until == _now() + timedelta(seconds=7.66)


def test_mapper_ignores_malformed_numeric_headers() -> None:
    snapshot = GroqRateLimitHeadersMapper().map_headers(
        headers={
            "x-ratelimit-remaining-requests": "not-a-number",
            "x-ratelimit-remaining-tokens": "-1",
            "retry-after": "bad",
        },
        observed_at=_now(),
    )

    assert snapshot.remaining_requests_day is None
    assert snapshot.remaining_tokens_minute is None
    assert snapshot.unavailable_until is None


def test_observed_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError):
        GroqRateLimitHeadersMapper().map_headers(
            headers={},
            observed_at=datetime(2026, 6, 8, 12, 0),
        )
