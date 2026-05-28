from __future__ import annotations

from typing import cast

import pytest
from groq import AsyncGroq

from src.infrastructure.config.settings import settings
from src.infrastructure.llm.groq_keyring import (
    GroqClientRotator,
    GroqKeySelection,
    _RotatingChatCompletionsProxy,
    configured_groq_api_keys,
    reset_groq_keyring_for_tests,
)
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


@pytest.mark.asyncio
async def test_groq_keyring_acquire_next_round_robins_configured_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GROQ_API_KEY", "unit-key-a")
    monkeypatch.setattr(settings, "GROQ_API_KEY2", "unit-key-b")
    monkeypatch.setattr(settings, "GROQ_API_KEY3", "unit-key-c")
    reset_groq_keyring_for_tests()

    from src.infrastructure.llm.groq_keyring import _GLOBAL_GROQ_KEYRING

    assert configured_groq_api_keys() == ("unit-key-a", "unit-key-b", "unit-key-c")
    selections = [await _GLOBAL_GROQ_KEYRING.acquire_next() for _ in range(4)]

    assert [selection.key for selection in selections] == [
        "unit-key-a",
        "unit-key-b",
        "unit-key-c",
        "unit-key-a",
    ]
    assert [selection.index for selection in selections] == [0, 1, 2, 0]
    assert all(selection.key_count == 3 for selection in selections)


@pytest.mark.asyncio
async def test_groq_keyring_deduplicates_configured_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GROQ_API_KEY", "unit-key-a")
    monkeypatch.setattr(settings, "GROQ_API_KEY2", "unit-key-a")
    monkeypatch.setattr(settings, "GROQ_API_KEY3", "unit-key-b")
    reset_groq_keyring_for_tests()

    assert configured_groq_api_keys() == ("unit-key-a", "unit-key-b")


def test_groq_route_observability_snapshot_aggregates_route_events() -> None:
    proxy = _RotatingChatCompletionsProxy(
        GroqClientRotator(client=cast(AsyncGroq, object()))
    )
    first_selection = GroqKeySelection(key="unit-key-a", index=0, key_count=2)
    second_selection = GroqKeySelection(key="unit-key-b", index=1, key_count=2)

    proxy._append_route_event(
        status="success",
        requested_model="llama-3.1-8b-instant",
        routed_model="llama-3.1-8b-instant",
        selection=first_selection,
        attempted_key_count=1,
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
    )
    proxy._append_route_event(
        status="success",
        requested_model="llama-3.1-8b-instant",
        routed_model="qwen/qwen3-32b",
        selection=second_selection,
        attempted_key_count=2,
        prompt_tokens=13,
        completion_tokens=5,
        total_tokens=18,
    )

    snapshot = proxy.route_observability_snapshot()

    assert snapshot["groq_route_event_count"] == 2
    assert snapshot["groq_route_success_count"] == 2
    assert snapshot["groq_route_fallback_count"] == 1
    assert snapshot["groq_key_slot_counts"] == {"1/2": 1, "2/2": 1}
    assert snapshot["groq_actual_model_counts"] == {
        "llama-3.1-8b-instant": 1,
        "qwen/qwen3-32b": 1,
    }
    assert snapshot["groq_fallback_reason_counts"] == {
        "model_fallback,key_rotation": 1,
    }
    assert snapshot["groq_last_route_event"] == {
        "sequence": 2,
        "status": "success",
        "requested_model": "llama-3.1-8b-instant",
        "routed_model": "qwen/qwen3-32b",
        "key_index": 1,
        "key_slot": 2,
        "key_count": 2,
        "key_slot_label": "2/2",
        "fallback_reason": "model_fallback,key_rotation",
        "limit_kind": "",
        "retry_after_seconds": None,
        "prompt_tokens": 13,
        "completion_tokens": 5,
        "total_tokens": 18,
        "error_type": "",
        "error": "",
    }
