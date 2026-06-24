from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmTaskCapacityProfile:
    profile_id: str
    estimated_prompt_tokens: int
    estimated_completion_tokens: int
    estimated_requests: int = 1

    def __post_init__(self) -> None:
        _require_non_empty_text(self.profile_id, field_name="profile_id")
        if not isinstance(self.estimated_prompt_tokens, int):
            raise TypeError("estimated_prompt_tokens must be int")
        if self.estimated_prompt_tokens <= 0:
            raise ValueError("estimated_prompt_tokens must be > 0")
        if not isinstance(self.estimated_completion_tokens, int):
            raise TypeError("estimated_completion_tokens must be int")
        if self.estimated_completion_tokens < 0:
            raise ValueError("estimated_completion_tokens must be >= 0")
        if not isinstance(self.estimated_requests, int):
            raise TypeError("estimated_requests must be int")
        if self.estimated_requests <= 0:
            raise ValueError("estimated_requests must be > 0")

    @property
    def estimated_input_tokens(self) -> int:
        return self.estimated_prompt_tokens

    @property
    def estimated_output_tokens(self) -> int:
        return self.estimated_completion_tokens

    @property
    def estimated_total_tokens(self) -> int:
        return self.estimated_input_tokens + self.estimated_output_tokens


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
