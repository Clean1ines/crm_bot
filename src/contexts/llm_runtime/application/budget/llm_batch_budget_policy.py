from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

from src.contexts.llm_runtime.domain.budget.prompt_profile import PromptProfile
from src.contexts.llm_runtime.domain.budget.provider_budget_profile import (
    ProviderBudgetProfile,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


@dataclass(frozen=True, slots=True)
class LlmBatchBudgetDecision:
    prompt_tokens: int
    batch_input_estimated_tokens: int
    batch_input_max_tokens: int
    request_input_estimated_tokens: int
    planned_output_reserve_tokens: int
    request_total_estimated_tokens: int
    request_safety_gap_tokens: int
    output_safety_gap_tokens: int
    request_output_cap_tokens: int | None

    def __post_init__(self) -> None:
        _require_positive_int(self.prompt_tokens, field_name="prompt_tokens")
        _require_non_negative_int(
            self.batch_input_estimated_tokens,
            field_name="batch_input_estimated_tokens",
        )
        _require_positive_int(
            self.batch_input_max_tokens,
            field_name="batch_input_max_tokens",
        )
        _require_positive_int(
            self.request_input_estimated_tokens,
            field_name="request_input_estimated_tokens",
        )
        _require_non_negative_int(
            self.planned_output_reserve_tokens,
            field_name="planned_output_reserve_tokens",
        )
        _require_positive_int(
            self.request_total_estimated_tokens,
            field_name="request_total_estimated_tokens",
        )
        _require_non_negative_int(
            self.request_safety_gap_tokens,
            field_name="request_safety_gap_tokens",
        )
        _require_non_negative_int(
            self.output_safety_gap_tokens,
            field_name="output_safety_gap_tokens",
        )
        if self.request_output_cap_tokens is not None:
            _require_positive_int(
                self.request_output_cap_tokens,
                field_name="request_output_cap_tokens",
            )

    @property
    def batch_input_fits(self) -> bool:
        return self.batch_input_estimated_tokens <= self.batch_input_max_tokens


@dataclass(frozen=True, slots=True)
class LlmBatchBudgetPolicy:
    provider_profile: ProviderBudgetProfile
    model_profile: ModelProfile
    prompt_profile: PromptProfile

    def __post_init__(self) -> None:
        if not isinstance(self.provider_profile, ProviderBudgetProfile):
            raise TypeError("provider_profile must be ProviderBudgetProfile")
        if not isinstance(self.model_profile, ModelProfile):
            raise TypeError("model_profile must be ModelProfile")
        if not isinstance(self.prompt_profile, PromptProfile):
            raise TypeError("prompt_profile must be PromptProfile")
        if self.model_profile.provider_id.value != self.provider_profile.provider_id:
            raise ValueError("model provider must match provider budget profile")
        if self.prompt_profile.provider_id != self.provider_profile.provider_id:
            raise ValueError("prompt provider must match provider budget profile")
        if self.prompt_profile.model_ref != self.model_profile.model_id.value:
            raise ValueError("prompt model_ref must match model profile")

    def decide(
        self,
        *,
        batch_input_char_count: int,
        observed_batch_input_tokens: int | None = None,
    ) -> LlmBatchBudgetDecision:
        _require_non_negative_int(
            batch_input_char_count,
            field_name="batch_input_char_count",
        )
        if observed_batch_input_tokens is not None:
            _require_non_negative_int(
                observed_batch_input_tokens,
                field_name="observed_batch_input_tokens",
            )

        batch_input_estimated_tokens = (
            observed_batch_input_tokens
            if observed_batch_input_tokens is not None
            else _estimate_batch_input_tokens(
                char_count=batch_input_char_count,
                char_to_token_multiplier=(
                    self.model_profile.model_char_to_token_multiplier
                ),
            )
        )
        prompt_tokens = self.prompt_profile.prompt_tokens
        model_tpm_limit = _model_tpm_limit(self.model_profile)
        request_safety_gap_tokens = self.provider_profile.request_safety_gap_tokens
        output_safety_gap_tokens = self.provider_profile.output_safety_gap_tokens
        available_tokens = model_tpm_limit - prompt_tokens - request_safety_gap_tokens
        if available_tokens <= 1:
            raise ValueError("model TPM budget is too small for prompt and safety gap")

        batch_input_max_tokens = available_tokens // 2
        planned_output_reserve_tokens = available_tokens - batch_input_max_tokens
        request_input_estimated_tokens = prompt_tokens + batch_input_estimated_tokens
        request_total_estimated_tokens = (
            request_input_estimated_tokens + planned_output_reserve_tokens
        )
        request_output_cap_tokens = _request_output_cap_tokens(
            provider_profile=self.provider_profile,
            model_profile=self.model_profile,
            model_tpm_limit=model_tpm_limit,
            request_input_estimated_tokens=request_input_estimated_tokens,
        )

        return LlmBatchBudgetDecision(
            prompt_tokens=prompt_tokens,
            batch_input_estimated_tokens=batch_input_estimated_tokens,
            batch_input_max_tokens=batch_input_max_tokens,
            request_input_estimated_tokens=request_input_estimated_tokens,
            planned_output_reserve_tokens=planned_output_reserve_tokens,
            request_total_estimated_tokens=request_total_estimated_tokens,
            request_safety_gap_tokens=request_safety_gap_tokens,
            output_safety_gap_tokens=output_safety_gap_tokens,
            request_output_cap_tokens=request_output_cap_tokens,
        )


def _estimate_batch_input_tokens(
    *,
    char_count: int,
    char_to_token_multiplier: Decimal,
) -> int:
    if char_count == 0:
        return 0
    return max(
        1,
        int(
            (Decimal(char_count) / char_to_token_multiplier).to_integral_value(
                rounding=ROUND_CEILING,
            )
        ),
    )


def _model_tpm_limit(model_profile: ModelProfile) -> int:
    tokens_per_minute = model_profile.rate_limits.tokens_per_minute
    if tokens_per_minute is None:
        raise ValueError("model profile must define tokens_per_minute")
    return tokens_per_minute


def _request_output_cap_tokens(
    *,
    provider_profile: ProviderBudgetProfile,
    model_profile: ModelProfile,
    model_tpm_limit: int,
    request_input_estimated_tokens: int,
) -> int | None:
    completion_remaining_tokens = (
        model_tpm_limit
        - request_input_estimated_tokens
        - provider_profile.output_safety_gap_tokens
    )
    if (
        completion_remaining_tokens
        <= provider_profile.provider_default_completion_tokens
    ):
        return None
    return min(completion_remaining_tokens, model_profile.max_output_tokens)


def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
