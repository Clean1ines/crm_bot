from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitProfile:
    requests_per_minute: int | None = None
    requests_per_day: int | None = None
    tokens_per_minute: int | None = None
    tokens_per_day: int | None = None
    input_tokens_per_minute: int | None = None
    output_tokens_per_minute: int | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("requests_per_minute", self.requests_per_minute),
            ("requests_per_day", self.requests_per_day),
            ("tokens_per_minute", self.tokens_per_minute),
            ("tokens_per_day", self.tokens_per_day),
            ("input_tokens_per_minute", self.input_tokens_per_minute),
            ("output_tokens_per_minute", self.output_tokens_per_minute),
        ):
            if value is not None and value <= 0:
                raise ValueError(
                    f"RateLimitProfile.{field_name} must be > 0 when provided"
                )
