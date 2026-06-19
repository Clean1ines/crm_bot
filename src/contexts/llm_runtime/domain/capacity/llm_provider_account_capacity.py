from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


@dataclass(frozen=True, slots=True)
class LlmProviderAccountCapacity:
    provider: str
    account_ref: str
    model_ref: str
    remaining_minute_requests: int
    remaining_minute_tokens: int
    remaining_daily_requests: int
    remaining_daily_tokens: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.provider, field_name="provider")
        _require_non_empty_text(self.account_ref, field_name="account_ref")
        _require_non_empty_text(self.model_ref, field_name="model_ref")
        for field_name, value in (
            ("remaining_minute_requests", self.remaining_minute_requests),
            ("remaining_minute_tokens", self.remaining_minute_tokens),
            ("remaining_daily_requests", self.remaining_daily_requests),
            ("remaining_daily_tokens", self.remaining_daily_tokens),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")

    def max_items_for(self, profile: LlmTaskCapacityProfile) -> int:
        if not isinstance(profile, LlmTaskCapacityProfile):
            raise TypeError("profile must be LlmTaskCapacityProfile")

        estimated_total_tokens = profile.estimated_total_tokens
        return min(
            self.remaining_minute_requests // profile.estimated_requests,
            self.remaining_minute_tokens // estimated_total_tokens,
            self.remaining_daily_requests // profile.estimated_requests,
            self.remaining_daily_tokens // estimated_total_tokens,
        )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
