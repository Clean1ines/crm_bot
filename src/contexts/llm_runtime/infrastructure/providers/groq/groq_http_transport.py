from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportResponse,
)


class GroqHttpClientResponse(Protocol):
    @property
    def status_code(self) -> int:
        """HTTP status code returned by the client."""

    @property
    def headers(self) -> dict[str, str]:
        """HTTP response headers."""

    def json(self) -> dict[str, JsonValue]:
        """Parse response JSON body."""


class GroqHttpClientPort(Protocol):
    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json_payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> GroqHttpClientResponse:
        """Send an HTTP POST request."""


@dataclass(frozen=True, slots=True)
class GroqApiKeyRef:
    """Non-empty API key value wrapper.

    This infrastructure value may contain the actual key. It must be passed
    explicitly by composition code and must not be read from env here.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("GroqApiKeyRef.value must be non-empty")


@dataclass(frozen=True, slots=True)
class GroqHttpTransport:
    """HTTP transport for Groq Chat Completions.

    This adapter does not own retry, fallback, route choice, quota policy, or
    workflow state. It only performs one HTTP request and returns raw response
    data to the provider adapter.
    """

    http_client: GroqHttpClientPort
    api_key: GroqApiKeyRef
    base_url: str = "https://api.groq.com/openai/v1"
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.base_url or not self.base_url.strip():
            raise ValueError("base_url must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")

    def post_chat_completions(
        self,
        *,
        payload: dict[str, JsonValue],
    ) -> GroqTransportResponse:
        response = self.http_client.post(
            url=f"{self.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key.value}",
                "Content-Type": "application/json",
            },
            json_payload=payload,
            timeout_seconds=self.timeout_seconds,
        )

        try:
            body = response.json()
        except ValueError:
            body = {
                "error": {
                    "message": "provider returned non-json response",
                },
            }

        return GroqTransportResponse(
            status_code=response.status_code,
            headers=response.headers,
            body=body,
        )
