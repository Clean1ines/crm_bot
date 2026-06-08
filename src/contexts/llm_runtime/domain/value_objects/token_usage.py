from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0:
            raise ValueError("TokenUsage.input_tokens must be >= 0")
        if self.output_tokens < 0:
            raise ValueError("TokenUsage.output_tokens must be >= 0")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
