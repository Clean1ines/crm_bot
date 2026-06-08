from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class WaitUntil:
    """UTC timestamp until which work should not be retried."""

    value: datetime

    def __post_init__(self) -> None:
        if self.value.tzinfo is None:
            raise ValueError("WaitUntil.value must be timezone-aware")
        if self.value.utcoffset() is None:
            raise ValueError("WaitUntil.value must be timezone-aware")

    @classmethod
    def now(cls) -> "WaitUntil":
        return cls(datetime.now(timezone.utc))
