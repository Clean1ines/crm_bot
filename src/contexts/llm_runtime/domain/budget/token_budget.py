from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

from src.contexts.llm_runtime.domain.budget.provider_budget_profile import (
    ProviderBudgetProfile,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


def artifact_tokens(char_count: int, model_profile: ModelProfile) -> int:
    _require_non_negative_int(char_count, field_name="char_count")
    if not isinstance(model_profile, ModelProfile):
        raise TypeError("model_profile must be ModelProfile")
    if char_count == 0:
        return 0
    return int(
        (
            Decimal(char_count) / model_profile.model_char_to_token_multiplier
        ).to_integral_value(rounding=ROUND_CEILING)
    )


def max_artifact_tokens(
    *,
    model_profile: ModelProfile,
    prompt_tokens: int,
    provider_profile: ProviderBudgetProfile,
) -> int:
    _require_positive_int(prompt_tokens, field_name="prompt_tokens")
    if not isinstance(model_profile, ModelProfile):
        raise TypeError("model_profile must be ModelProfile")
    if not isinstance(provider_profile, ProviderBudgetProfile):
        raise TypeError("provider_profile must be ProviderBudgetProfile")

    model_tpm = _required_model_tpm(model_profile)
    available_tokens = (
        model_tpm - prompt_tokens - provider_profile.request_safety_gap_tokens
    )
    if available_tokens <= 0:
        raise ValueError("prompt_tokens and safety gap exceed model TPM")
    return available_tokens // 2


def input_tokens(*, prompt_tokens: int, artifact_tokens: int) -> int:
    _require_positive_int(prompt_tokens, field_name="prompt_tokens")
    _require_non_negative_int(artifact_tokens, field_name="artifact_tokens")
    return prompt_tokens + artifact_tokens


def required_window_tokens(
    *,
    input_tokens: int,
    artifact_tokens: int,
    safety_gap_tokens: int,
) -> int:
    _require_positive_int(input_tokens, field_name="input_tokens")
    _require_non_negative_int(artifact_tokens, field_name="artifact_tokens")
    _require_non_negative_int(safety_gap_tokens, field_name="safety_gap_tokens")
    return input_tokens + artifact_tokens + safety_gap_tokens


def max_completion_tokens(
    *,
    remaining_after_input_tokens: int,
    provider_profile: ProviderBudgetProfile,
    model_profile: ModelProfile,
) -> int | None:
    _require_int(
        remaining_after_input_tokens,
        field_name="remaining_after_input_tokens",
    )
    if not isinstance(provider_profile, ProviderBudgetProfile):
        raise TypeError("provider_profile must be ProviderBudgetProfile")
    if not isinstance(model_profile, ModelProfile):
        raise TypeError("model_profile must be ModelProfile")

    if (
        remaining_after_input_tokens
        <= provider_profile.provider_default_completion_tokens
    ):
        return None

    return min(
        remaining_after_input_tokens,
        _required_model_max_output_tokens(model_profile),
    )


def _required_model_tpm(model_profile: ModelProfile) -> int:
    value = model_profile.rate_limits.tokens_per_minute
    if value is None:
        raise ValueError(
            "model_profile.rate_limits.tokens_per_minute must be configured"
        )
    _require_positive_int(value, field_name="tokens_per_minute")
    return value


def _required_model_max_output_tokens(model_profile: ModelProfile) -> int:
    value = model_profile.max_output_tokens
    _require_positive_int(value, field_name="max_output_tokens")
    return value


def _require_positive_int(value: int, *, field_name: str) -> None:
    _require_int(value, field_name=field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    _require_int(value, field_name=field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
