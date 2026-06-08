from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmInputRef:
    """Opaque reference to prepared input owned by the caller/application layer."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("LlmInputRef.value must be non-empty")
