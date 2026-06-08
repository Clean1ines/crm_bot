from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Generic retry policy for work execution."""

    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int

    def __post_init__(self) -> None:
        if self.max_attempts < 0:
            raise ValueError("RetryPolicy.max_attempts must be >= 0")
        if self.base_delay_seconds < 0:
            raise ValueError("RetryPolicy.base_delay_seconds must be >= 0")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                "RetryPolicy.max_delay_seconds must be >= base_delay_seconds"
            )

    def can_retry(self, attempt_count: int) -> bool:
        return attempt_count < self.max_attempts

    def delay_for_attempt(self, attempt_count: int) -> int:
        if self.base_delay_seconds == 0:
            return 0
        delay = self.base_delay_seconds * (2 ** max(attempt_count - 1, 0))
        return min(delay, self.max_delay_seconds)
