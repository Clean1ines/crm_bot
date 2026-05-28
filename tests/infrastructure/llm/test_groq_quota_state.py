from __future__ import annotations

import pytest

from src.infrastructure.config.settings import settings
from src.infrastructure.llm.groq_quota_state import (
    GroqRouteQuotaBlockedError,
    clear_groq_route_quota_state,
    get_groq_route_quota_state,
    groq_route_quota_identity,
    record_groq_route_failure,
    record_groq_route_success,
    wait_or_block_groq_route,
)
from src.infrastructure.llm.groq_router import GroqLimitKind


@pytest.mark.asyncio
async def test_groq_quota_state_blocks_without_storing_raw_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "")
    raw_key = "unit-test-groq-key-value"
    identity = groq_route_quota_identity(
        api_key=raw_key,
        key_index=1,
        key_count=3,
        model="llama-3.1-8b-instant",
    )

    assert raw_key not in identity.redis_key
    assert "llama-3.1-8b-instant" in identity.redis_key

    await clear_groq_route_quota_state(identity)
    await record_groq_route_failure(
        identity=identity,
        limit_kind=GroqLimitKind.TPD,
        retry_after_seconds=None,
        error="tokens per day quota exhausted",
    )

    state = await get_groq_route_quota_state(identity)
    assert state is not None
    assert state.limit_kind == GroqLimitKind.TPD.value
    assert state.is_blocking_now
    assert state.remaining_seconds > 60 * 60

    with pytest.raises(GroqRouteQuotaBlockedError) as exc_info:
        await wait_or_block_groq_route(identity)

    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after > 60 * 60
    assert "groq_quota_exhausted" in str(exc_info.value)

    await record_groq_route_success(identity)
    assert await get_groq_route_quota_state(identity) is None


@pytest.mark.asyncio
async def test_groq_quota_state_ignores_non_limit_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "")
    identity = groq_route_quota_identity(
        api_key="unit-test-groq-key-value",
        key_index=0,
        key_count=1,
        model="qwen/qwen3-32b",
    )

    await clear_groq_route_quota_state(identity)
    await record_groq_route_failure(
        identity=identity,
        limit_kind=GroqLimitKind.REQUEST_TOO_LARGE,
        retry_after_seconds=None,
        error="request too large",
    )

    assert await get_groq_route_quota_state(identity) is None
