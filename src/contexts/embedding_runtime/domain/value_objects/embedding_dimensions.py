from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingDimensions:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("EmbeddingDimensions.value must be > 0")
