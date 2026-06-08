from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LlmProviderMessageRole(StrEnum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class LlmProviderMessage:
    role: LlmProviderMessageRole
    content: str

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("LlmProviderMessage.content must be non-empty")


@dataclass(frozen=True, slots=True)
class LlmProviderInput:
    messages: tuple[LlmProviderMessage, ...]

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("LlmProviderInput.messages must not be empty")
