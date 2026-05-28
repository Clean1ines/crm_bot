from __future__ import annotations

import pytest

from src.infrastructure.config.settings import settings
from src.infrastructure.llm.groq_quota_state import (
    GroqRouteQuotaBlockedError,
    clear_groq_route_quota_state,
    get_groq_route_observability,
    get_groq_route_quota_state,
    groq_route_quota_identity,
    record_groq_route_failure,
    record_groq_route_success,
    wait_or_block_groq_route,
)
from src.infrastructure.llm.groq_router import GroqLimitKind


@pytest.mark.asyncio
async def test_groq_success_headers_persist_remaining_and_reset_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "")
    identity = groq_route_quota_identity(
        api_key="scheduler-test-key",
        key_index=0,
        key_count=1,
        model="llama-3.1-8b-instant",
    )
    await clear_groq_route_quota_state(identity)

    await record_groq_route_success(
        identity,
        headers_source={
            "x-ratelimit-limit-requests": "100",
            "x-ratelimit-remaining-requests": "77",
            "x-ratelimit-reset-requests": "10s",
            "x-ratelimit-limit-tokens": "6000",
            "x-ratelimit-remaining-tokens": "5000",
            "x-ratelimit-reset-tokens": "1s",
        },
    )

    state = await get_groq_route_quota_state(identity)
    assert state is not None
    assert state.limit_kind == GroqLimitKind.NONE.value
    assert state.limit_requests == 100
    assert state.remaining_requests == 77
    assert state.limit_tokens == 6000
    assert state.remaining_tokens == 5000
    assert not state.is_blocking_now

    observability = await get_groq_route_observability(identity)
    assert observability["remaining_requests"] == 77
    assert observability["remaining_tokens"] == 5000

    await clear_groq_route_quota_state(identity)


@pytest.mark.asyncio
async def test_groq_success_headers_block_route_when_remaining_requests_are_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "")
    identity = groq_route_quota_identity(
        api_key="scheduler-test-key",
        key_index=0,
        key_count=1,
        model="llama-3.1-8b-instant",
    )
    await clear_groq_route_quota_state(identity)

    await record_groq_route_success(
        identity,
        headers_source={
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "2h",
        },
    )

    state = await get_groq_route_quota_state(identity)
    assert state is not None
    assert state.remaining_requests == 0
    assert state.is_blocking_now
    assert state.remaining_seconds > 60 * 60

    with pytest.raises(GroqRouteQuotaBlockedError) as exc_info:
        await wait_or_block_groq_route(identity)

    assert exc_info.value.retry_after > 60 * 60

    await clear_groq_route_quota_state(identity)


@pytest.mark.asyncio
async def test_groq_failure_uses_retry_after_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "")
    identity = groq_route_quota_identity(
        api_key="scheduler-test-key",
        key_index=0,
        key_count=1,
        model="llama-3.1-8b-instant",
    )
    await clear_groq_route_quota_state(identity)

    await record_groq_route_failure(
        identity=identity,
        limit_kind=GroqLimitKind.RPM,
        retry_after_seconds=None,
        error="rate limited",
        headers_source={"retry-after": "2h"},
    )

    state = await get_groq_route_quota_state(identity)
    assert state is not None
    assert state.retry_after_seconds == 7200.0
    assert state.remaining_seconds > 60 * 60

    with pytest.raises(GroqRouteQuotaBlockedError):
        await wait_or_block_groq_route(identity)

    await clear_groq_route_quota_state(identity)
