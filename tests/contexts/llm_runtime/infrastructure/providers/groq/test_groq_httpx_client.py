from __future__ import annotations

import httpx
import pytest

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_httpx_client import (
    GroqHttpxClient,
    GroqHttpxResponseAdapter,
)


def test_httpx_response_adapter_exposes_status_headers_and_json_body() -> None:
    response = httpx.Response(
        status_code=200,
        headers={"x-ratelimit-remaining-tokens": "5999"},
        json={
            "choices": [
                {
                    "message": {
                        "content": '{"ok": true}',
                    },
                },
            ],
        },
    )

    adapter = GroqHttpxResponseAdapter(response=response)

    assert adapter.status_code == 200
    assert adapter.headers["x-ratelimit-remaining-tokens"] == "5999"
    assert adapter.json() == {
        "choices": [
            {
                "message": {"content": '{"ok": true}'},
            },
        ],
    }


def test_httpx_response_adapter_rejects_non_object_json_body() -> None:
    response = httpx.Response(
        status_code=200,
        json=["not", "an", "object"],
    )

    adapter = GroqHttpxResponseAdapter(response=response)

    with pytest.raises(ValueError):
        adapter.json()


def test_httpx_client_posts_payload_through_mock_transport() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            status_code=200,
            headers={"x-ratelimit-remaining-requests": "999"},
            json={"ok": True},
        )

    response = GroqHttpxClient(
        transport=httpx.MockTransport(handler),
    ).post(
        url="https://api.groq.test/openai/v1/chat/completions",
        headers={
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        },
        json_payload={
            "model": "qwen/qwen3-32b",
            "messages": [{"role": "user", "content": "Return JSON."}],
        },
        timeout_seconds=12.5,
    )

    assert response.status_code == 200
    assert response.headers["x-ratelimit-remaining-requests"] == "999"
    assert response.json() == {"ok": True}

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert str(request.url) == "https://api.groq.test/openai/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["content-type"] == "application/json"
    assert b"qwen/qwen3-32b" in request.content
