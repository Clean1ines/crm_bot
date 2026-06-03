from __future__ import annotations

from dataclasses import dataclass

from .limits import LlmModelLimits
from .shared import ModelName, ProviderId, require_non_empty


@dataclass(frozen=True, slots=True)
class LlmModelProfile:
    provider_id: ProviderId
    model: ModelName
    display_name: str
    limits: LlmModelLimits
    supports_json_object: bool
    supports_tools: bool = False
    supports_streaming: bool = False
    enabled: bool = True

    def __post_init__(self) -> None:
        require_non_empty(self.provider_id, field_name="provider_id")
        require_non_empty(self.model, field_name="model")
        require_non_empty(self.display_name, field_name="display_name")
