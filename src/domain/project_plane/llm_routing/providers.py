from __future__ import annotations

from dataclasses import dataclass

from .shared import ProviderId, require_non_empty


@dataclass(frozen=True, slots=True)
class LlmProvider:
    provider_id: ProviderId
    display_name: str
    enabled: bool = True

    def __post_init__(self) -> None:
        require_non_empty(self.provider_id, field_name="provider_id")
        require_non_empty(self.display_name, field_name="display_name")
