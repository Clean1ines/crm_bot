from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infrastructure.llm import completion_client


class _Response:
    content = " generated "


class _Client:
    async def ainvoke(self, messages: list[tuple[str, str]]) -> _Response:
        assert messages == [("human", "prompt")]
        return _Response()


@pytest.mark.parametrize(
    ("requested_model", "expected_model"),
    [
        (None, "openai/gpt-oss-120b"),
        ("openai/gpt-oss-120b", "openai/gpt-oss-120b"),
        ("openai/gpt-oss-20b", "openai/gpt-oss-20b"),
        ("qwen/qwen3.6-27b", "openai/gpt-oss-120b"),
        ("unknown-model", "openai/gpt-oss-120b"),
    ],
)
def test_completion_client_uses_only_supported_gpt_oss_models(
    monkeypatch: pytest.MonkeyPatch,
    requested_model: str | None,
    expected_model: str,
) -> None:
    captured: dict[str, object] = {}

    def factory(**kwargs: object) -> _Client:
        captured.update(kwargs)
        return _Client()

    monkeypatch.setattr(
        completion_client,
        "settings",
        SimpleNamespace(
            GROQ_API_KEY="test-key",
            GROQ_MODEL="llama-3.1-8b-instant",
        ),
    )
    monkeypatch.setattr(completion_client, "ChatGroq", factory)

    result = asyncio.run(
        completion_client.GroqTextCompletionClient().complete(
            "prompt",
            model_name=requested_model,
        )
    )

    assert result == "generated"
    assert captured["model"] == expected_model
    assert captured["model_kwargs"] == {"include_reasoning": False}
    assert captured["reasoning_effort"] == "low"
