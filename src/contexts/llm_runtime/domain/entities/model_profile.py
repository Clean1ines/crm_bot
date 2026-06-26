from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.model_lifecycle import ModelLifecycle
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.rate_limit_profile import (
    RateLimitProfile,
)
from src.contexts.llm_runtime.domain.value_objects.reasoning_profile import (
    ReasoningProfile,
)
from src.contexts.llm_runtime.domain.value_objects.token_price import TokenPrice


@dataclass(frozen=True, slots=True)
class ModelProfile:
    provider_id: ProviderId
    model_id: ModelId
    lifecycle: ModelLifecycle
    context_window_tokens: int
    max_output_tokens: int
    model_rank: int
    rate_limits: RateLimitProfile
    token_price: TokenPrice
    reasoning_profile: ReasoningProfile
    supports_json_object: bool = True
    supports_json_schema: bool = False
    enabled: bool = True
    model_char_to_token_multiplier: Decimal = Decimal("4.0")

    def __post_init__(self) -> None:
        if self.context_window_tokens <= 0:
            raise ValueError("ModelProfile.context_window_tokens must be > 0")
        if self.max_output_tokens <= 0:
            raise ValueError("ModelProfile.max_output_tokens must be > 0")
        if self.max_output_tokens > self.context_window_tokens:
            raise ValueError(
                "ModelProfile.max_output_tokens must be <= context_window_tokens"
            )
        if self.model_rank < 0:
            raise ValueError("ModelProfile.model_rank must be >= 0")
        if not isinstance(self.model_char_to_token_multiplier, Decimal):
            raise TypeError(
                "ModelProfile.model_char_to_token_multiplier must be Decimal"
            )
        if self.model_char_to_token_multiplier <= 0:
            raise ValueError("ModelProfile.model_char_to_token_multiplier must be > 0")

    @property
    def can_disable_reasoning(self) -> bool:
        return self.reasoning_profile.can_disable_reasoning
