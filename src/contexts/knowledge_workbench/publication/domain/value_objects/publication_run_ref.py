from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PublicationRunRef:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("PublicationRunRef.value must be non-empty")
