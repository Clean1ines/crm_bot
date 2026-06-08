from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_transport import (
    GroqHttpClientPort,
    GroqHttpClientResponse,
)


@dataclass(frozen=True, slots=True)
class GroqHttpxResponseAdapter(GroqHttpClientResponse):
    response: httpx.Response

    @property
    def status_code(self) -> int:
        return self.response.status_code

    @property
    def headers(self) -> dict[str, str]:
        return dict(self.response.headers)

    def json(self) -> dict[str, JsonValue]:
        parsed = self.response.json()
        if not isinstance(parsed, dict):
            raise ValueError("Groq HTTP response JSON body must be an object")
        return parsed


@dataclass(frozen=True, slots=True)
class GroqHttpxClient(GroqHttpClientPort):
    """Synchronous httpx client adapter for Groq HTTP transport.

    This class performs exactly one HTTP POST. It does not own retry, fallback,
    quota, route selection, env loading, key rotation, or workflow policy.
    """

    transport: httpx.BaseTransport | None = None

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json_payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> GroqHttpClientResponse:
        with httpx.Client(
            timeout=timeout_seconds,
            transport=self.transport,
        ) as client:
            response = client.post(
                url,
                headers=headers,
                json=json_payload,
            )

        return GroqHttpxResponseAdapter(response=response)
