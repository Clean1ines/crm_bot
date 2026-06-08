from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderId:
    value: str

    def __post_init__(self) -> None:
        value = self.value.strip() if self.value else ""
        if not value:
            raise ValueError("ProviderId.value must be non-empty")
        if " " in value:
            raise ValueError("ProviderId.value must not contain spaces")
        if value != value.lower():
            raise ValueError("ProviderId.value must be lowercase")
