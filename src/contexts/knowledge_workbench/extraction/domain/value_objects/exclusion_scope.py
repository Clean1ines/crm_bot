from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExclusionScope:
    value: str

    def __post_init__(self) -> None:
        if self.value is None:
            raise ValueError("ExclusionScope.value must not be None")
