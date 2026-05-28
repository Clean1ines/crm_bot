from __future__ import annotations

import pytest

from src.infrastructure.config.settings import settings
from src.infrastructure.llm import groq_keyring
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


class _Completions:
    def __init__(self, api_key: str, calls: list[tuple[str, str]]) -> None:
        self._api_key = api_key
        self._calls = calls

    async def create(self, *args: object, **kwargs: object) -> _Response:
        self._calls.append((self._api_key, str(kwargs.get("model"))))
        return _Response()


class _Chat:
    def __init__(self, api_key: str, calls: list[tuple[str, str]]) -> None:
        self.completions = _Completions(api_key, calls)


class _Client:
    calls: list[tuple[str, str]] = []

    def __init__(self, *, api_key: str) -> None:
        self.chat = _Chat(api_key, self.calls)


@pytest.mark.asyncio
async def test_rotating_async_groq_chat_create_uses_round_robin_key_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "primary-test-key")
    monkeypatch.setattr(settings, "GROQ_API_KEY2", "secondary-test-key")
    monkeypatch.setattr(settings, "GROQ_API_KEY3", None)
    monkeypatch.setattr(groq_keyring, "AsyncGroq", _Client)
    _Client.calls = []
    reset_groq_keyring_for_tests()

    client = RotatingAsyncGroq()
    await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "one"}],
    )
    await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "two"}],
    )

    assert _Client.calls == [
        ("primary-test-key", "llama-3.1-8b-instant"),
        ("secondary-test-key", "llama-3.1-8b-instant"),
    ]
    snapshot = client.route_observability_snapshot()
    assert snapshot["groq_key_slot_counts"] == {"1/2": 1, "2/2": 1}
    assert snapshot["groq_actual_model_counts"] == {"llama-3.1-8b-instant": 2}
