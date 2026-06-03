from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .shared import ApiKeySlot, ProviderId, require_non_empty


class LlmApiKeySlotStatus(StrEnum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    EXHAUSTED_TODAY = "exhausted_today"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class LlmApiKeySlot:
    provider_id: ProviderId
    slot: ApiKeySlot
    status: LlmApiKeySlotStatus
    cooldown_seconds: int | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.provider_id, field_name="provider_id")
        require_non_empty(self.slot, field_name="slot")
        if self.cooldown_seconds is not None and self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be non-negative")
