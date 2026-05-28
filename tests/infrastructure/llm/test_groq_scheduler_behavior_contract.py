from __future__ import annotations

import pytest

from src.infrastructure.config.settings import settings
from src.infrastructure.llm import groq_keyring, groq_quota_state
from src.infrastructure.llm.groq_keyring import (
    RotatingAsyncGroq,
    reset_groq_keyring_for_tests,
)


class _Usage:
    prompt_tokens = 11
    completion_tokens = 7
    total_tokens = 18


class _Message:
    content = "{}"


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]
    usage = _Usage()

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


class _Completions:
    def __init__(self, api_key: str, calls: list[tuple[str, str]]) -> None:
        self._api_key = api_key
        self._calls = calls

    async def create(self, *args: object, **kwargs: object) -> _Response:
        self._calls.append((self._api_key, str(kwargs.get("model"))))
        return _Response(dict(_Client.response_headers))


class _Chat:
    def __init__(self, api_key: str, calls: list[tuple[str, str]]) -> None:
        self.completions = _Completions(api_key, calls)


class _Client:
    calls: list[tuple[str, str]] = []
    response_headers: dict[str, str] = {}

    def __init__(self, *, api_key: str) -> None:
        self.chat = _Chat(api_key, self.calls)


@pytest.mark.asyncio
async def test_success_headers_remaining_zero_block_next_same_key_model_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "primary-test-key")
    monkeypatch.setattr(settings, "GROQ_API_KEY2", None)
    monkeypatch.setattr(settings, "GROQ_API_KEY3", None)
    monkeypatch.setattr(groq_keyring, "AsyncGroq", _Client)

    _Client.calls = []
    _Client.response_headers = {
        "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-requests": "2h",
    }
    groq_quota_state._MEMORY_STORE.states.clear()
    reset_groq_keyring_for_tests()

    client = RotatingAsyncGroq()
    await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "one"}],
    )

    try:
        await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "two"}],
        )
    except Exception:
        pass

    instant_route_calls = [
        call
        for call in _Client.calls
        if call == ("primary-test-key", "llama-3.1-8b-instant")
    ]
    assert instant_route_calls == [("primary-test-key", "llama-3.1-8b-instant")]

    snapshot = client.route_observability_snapshot()
    assert snapshot["groq_route_event_count"] >= 2
    assert snapshot["groq_route_cooldown_block_count"] >= 1
