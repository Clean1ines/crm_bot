from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelId:
    value: str

    def __post_init__(self) -> None:
        value = self.value.strip() if self.value else ""
        if not value:
            raise ValueError("ModelId.value must be non-empty")
        if " " in value:
            raise ValueError("ModelId.value must not contain spaces")
