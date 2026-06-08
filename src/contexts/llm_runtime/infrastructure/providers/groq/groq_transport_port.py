from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)


@dataclass(frozen=True, slots=True)
class GroqTransportResponse:
    status_code: int
    headers: dict[str, str]
    body: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if self.status_code < 100:
            raise ValueError("status_code must be a valid HTTP status code")


class GroqTransportPort(Protocol):
    def post_chat_completions(
        self,
        *,
        payload: dict[str, JsonValue],
    ) -> GroqTransportResponse:
        """Send a prepared Groq chat completions payload."""
