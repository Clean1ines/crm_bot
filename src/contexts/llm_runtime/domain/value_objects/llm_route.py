from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId


@dataclass(frozen=True, slots=True)
class LlmRoute:
    provider_id: ProviderId
    model_id: ModelId
    account_ref: ProviderAccountRef
