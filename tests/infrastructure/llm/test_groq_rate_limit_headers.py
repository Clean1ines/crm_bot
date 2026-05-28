from __future__ import annotations

from src.infrastructure.llm.groq_rate_limit_headers import (
    groq_rate_limit_headers_from_source,
    parse_groq_reset_seconds,
)


def test_parse_groq_reset_seconds_accepts_compound_duration() -> None:
    assert parse_groq_reset_seconds("2m59.56s") == 179.56
    assert parse_groq_reset_seconds("1h2m3s") == 3723.0
    assert parse_groq_reset_seconds("500ms") == 0.5


def test_groq_rate_limit_headers_from_mapping() -> None:
    headers = groq_rate_limit_headers_from_source(
        {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "2m",
            "x-ratelimit-limit-tokens": "6000",
            "x-ratelimit-remaining-tokens": "10",
            "x-ratelimit-reset-tokens": "1s",
            "retry-after": "3",
        }
    )

    assert headers.limit_requests == 1000
    assert headers.remaining_requests == 0
    assert headers.reset_requests_seconds == 120.0
    assert headers.limit_tokens == 6000
    assert headers.remaining_tokens == 10
    assert headers.reset_tokens_seconds == 1.0
    assert headers.retry_after_seconds == 3.0
    assert headers.blocking_reset_seconds == 120.0


def test_groq_rate_limit_headers_are_case_insensitive() -> None:
    headers = groq_rate_limit_headers_from_source(
        {
            "X-RateLimit-Remaining-Requests": "7",
            "X-RateLimit-Reset-Requests": "10s",
        }
    )

    assert headers.remaining_requests == 7
    assert headers.reset_requests_seconds == 10.0
