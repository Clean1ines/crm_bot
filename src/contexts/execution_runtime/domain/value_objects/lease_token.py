from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class LeaseToken:
    """Opaque token proving ownership of a leased work item."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("LeaseToken.value must be non-empty")

    @classmethod
    def new(cls) -> "LeaseToken":
        return cls(str(uuid4()))
