from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_transport import (
    GroqApiKeyRef,
    GroqHttpTransport,
)


@dataclass(frozen=True, slots=True)
class FakeHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: dict[str, JsonValue]
    json_fails: bool = False

    def json(self) -> dict[str, JsonValue]:
        if self.json_fails:
            raise ValueError("not json")
        return self.body


@dataclass(slots=True)
class FakeHttpClient:
    response: FakeHttpResponse
    captured_posts: list[tuple[str, dict[str, str], dict[str, JsonValue], float]] = (
        field(
            default_factory=list,
        )
    )

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json_payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> FakeHttpResponse:
        self.captured_posts.append((url, headers, json_payload, timeout_seconds))
        return self.response


def test_http_transport_posts_chat_completion_payload_with_auth_header() -> None:
    client = FakeHttpClient(
        response=FakeHttpResponse(
            status_code=200,
            headers={"x-ratelimit-remaining-tokens": "5999"},
            body={"choices": [{"message": {"content": '{"ok": true}'}}]},
        ),
    )
    transport = GroqHttpTransport(
        http_client=client,
        api_key=GroqApiKeyRef("secret-key"),
        timeout_seconds=12.5,
    )

    response = transport.post_chat_completions(
        payload={
            "model": "qwen/qwen3-32b",
            "messages": [{"role": "user", "content": "Return JSON."}],
        },
    )

    assert response.status_code == 200
    assert response.headers == {"x-ratelimit-remaining-tokens": "5999"}
    assert response.body == {"choices": [{"message": {"content": '{"ok": true}'}}]}

    assert len(client.captured_posts) == 1
    url, headers, json_payload, timeout_seconds = client.captured_posts[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert headers == {
        "Authorization": "Bearer secret-key",
        "Content-Type": "application/json",
    }
    assert json_payload["model"] == "qwen/qwen3-32b"
    assert timeout_seconds == 12.5


def test_http_transport_allows_custom_base_url_without_trailing_slash_issues() -> None:
    client = FakeHttpClient(
        response=FakeHttpResponse(status_code=200, headers={}, body={}),
    )
    transport = GroqHttpTransport(
        http_client=client,
        api_key=GroqApiKeyRef("secret-key"),
        base_url="https://example.test/",
    )

    transport.post_chat_completions(payload={"model": "m"})

    assert client.captured_posts[0][0] == "https://example.test/chat/completions"


def test_http_transport_turns_non_json_body_into_error_body() -> None:
    client = FakeHttpClient(
        response=FakeHttpResponse(
            status_code=502,
            headers={},
            body={},
            json_fails=True,
        ),
    )
    transport = GroqHttpTransport(
        http_client=client,
        api_key=GroqApiKeyRef("secret-key"),
    )

    response = transport.post_chat_completions(payload={"model": "m"})

    assert response.status_code == 502
    assert response.body == {
        "error": {
            "message": "provider returned non-json response",
        },
    }


def test_http_transport_validates_configuration() -> None:
    client = FakeHttpClient(
        response=FakeHttpResponse(status_code=200, headers={}, body={}),
    )

    with pytest.raises(ValueError):
        GroqApiKeyRef("")

    with pytest.raises(ValueError):
        GroqHttpTransport(
            http_client=client,
            api_key=GroqApiKeyRef("secret-key"),
            base_url="",
        )

    with pytest.raises(ValueError):
        GroqHttpTransport(
            http_client=client,
            api_key=GroqApiKeyRef("secret-key"),
            timeout_seconds=0,
        )
