from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from src.contexts.llm_runtime.domain.budget.llm_phase_operation_profile import (
    LlmPhaseOperationProfile,
)
from src.contexts.llm_runtime.domain.budget.prompt_profile import PromptProfile
from src.contexts.llm_runtime.domain.budget.provider_budget_profile import (
    ProviderBudgetProfile,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


@dataclass(frozen=True, slots=True)
class LlmPhaseTokenBudget:
    provider: str
    model_ref: str
    model_tpm_limit: int
    model_char_to_token_multiplier: Decimal
    prompt_id: str
    prompt_version: str
    prompt_tokens: int
    phase: str
    operation: str
    input_artifact_kind: str
    output_artifact_kind: str
    request_safety_gap_tokens: int
    output_safety_gap_tokens: int
    provider_default_completion_tokens: int
    artifact_token_estimate: int
    capacity_window_remaining_tokens: int
    max_artifact_input_tokens: int
    planned_output_reserve_tokens: int
    request_input_estimated_tokens: int
    remaining_after_estimated_input_tokens: int
    effective_output_cap_tokens: int
    request_output_cap_tokens: int | None
    reserved_total_tokens: int

    @property
    def estimated_total_tokens(self) -> int:
        return self.request_input_estimated_tokens + self.planned_output_reserve_tokens

    def to_capacity_estimate_payload(
        self,
        *,
        estimator: str,
        extra_metadata: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "budget_contract_version": "v1",
            "estimator": estimator,
            "provider": self.provider,
            "model_ref": self.model_ref,
            "model_tpm_limit": self.model_tpm_limit,
            "model_char_to_token_multiplier": str(self.model_char_to_token_multiplier),
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_tokens": self.prompt_tokens,
            "phase": self.phase,
            "operation": self.operation,
            "input_artifact_kind": self.input_artifact_kind,
            "output_artifact_kind": self.output_artifact_kind,
            "request_safety_gap_tokens": self.request_safety_gap_tokens,
            "output_safety_gap_tokens": self.output_safety_gap_tokens,
            "provider_default_completion_tokens": (
                self.provider_default_completion_tokens
            ),
            "artifact_token_estimate": self.artifact_token_estimate,
            "batch_input_estimated_tokens": self.artifact_token_estimate,
            "max_artifact_input_tokens": self.max_artifact_input_tokens,
            "batch_input_max_tokens": self.max_artifact_input_tokens,
            "planned_output_reserve_tokens": self.planned_output_reserve_tokens,
            "request_input_estimated_tokens": self.request_input_estimated_tokens,
            "capacity_window_remaining_tokens": (self.capacity_window_remaining_tokens),
            "remaining_after_estimated_input_tokens": (
                self.remaining_after_estimated_input_tokens
            ),
            "remaining_after_actual_input_tokens": (
                self.remaining_after_estimated_input_tokens
            ),
            "effective_output_cap_tokens": self.effective_output_cap_tokens,
            "estimated_total_tokens": self.estimated_total_tokens,
            "request_total_estimated_tokens": self.estimated_total_tokens,
            "reserved_total_tokens": self.reserved_total_tokens,
            # legacy compatibility keys
            "prompt_message_tokens": (self.prompt_tokens,),
            "estimated_input_tokens": self.request_input_estimated_tokens,
            "estimated_output_tokens": self.planned_output_reserve_tokens,
        }
        if self.request_output_cap_tokens is not None:
            payload["request_output_cap_tokens"] = self.request_output_cap_tokens
        if extra_metadata is not None:
            payload.update(dict(extra_metadata))
        return payload


@dataclass(frozen=True, slots=True)
class LlmPhaseTokenBudgetPolicy:
    provider_profile: ProviderBudgetProfile
    model_profile: ModelProfile
    prompt_profile: PromptProfile
    operation_profile: LlmPhaseOperationProfile

    def __post_init__(self) -> None:
        _validate_profile_contract(
            provider_profile=self.provider_profile,
            model_profile=self.model_profile,
            prompt_profile=self.prompt_profile,
            operation_profile=self.operation_profile,
        )

    def estimate_artifact_tokens_from_chars(self, char_count: int) -> int:
        if isinstance(char_count, bool) or not isinstance(char_count, int):
            raise TypeError("char_count must be int")
        if char_count < 0:
            raise ValueError("char_count must be >= 0")
        if char_count == 0:
            return 0

        multiplier = self.model_profile.model_char_to_token_multiplier
        token_count = (Decimal(char_count) / multiplier).to_integral_value(
            rounding=ROUND_CEILING,
        )
        return max(1, int(token_count))

    def calculate_for_artifact_tokens(
        self,
        artifact_token_estimate: int,
        *,
        capacity_window_remaining_tokens: int | None = None,
    ) -> LlmPhaseTokenBudget:
        if (
            isinstance(artifact_token_estimate, bool)
            or not isinstance(artifact_token_estimate, int)
            or artifact_token_estimate < 0
        ):
            raise ValueError("artifact_token_estimate must be non-negative int")

        model_tpm_limit = _model_tpm_limit(self.model_profile)
        prompt_tokens = self.prompt_profile.prompt_tokens
        request_safety_gap_tokens = self.provider_profile.request_safety_gap_tokens

        available_for_artifact_and_output = (
            model_tpm_limit - prompt_tokens - request_safety_gap_tokens
        )
        if available_for_artifact_and_output <= 0:
            raise ValueError(
                "model_tpm_limit must leave budget after prompt and request safety gap"
            )

        max_artifact_input_tokens = available_for_artifact_and_output // 2
        planned_output_reserve_tokens = (
            available_for_artifact_and_output - max_artifact_input_tokens
        )
        request_input_estimated_tokens = prompt_tokens + artifact_token_estimate

        effective_window_remaining_tokens = (
            model_tpm_limit
            if capacity_window_remaining_tokens is None
            else capacity_window_remaining_tokens
        )
        if (
            isinstance(effective_window_remaining_tokens, bool)
            or not isinstance(effective_window_remaining_tokens, int)
            or effective_window_remaining_tokens <= 0
        ):
            raise ValueError("capacity_window_remaining_tokens must be positive int")

        remaining_after_estimated_input_tokens = max(
            0,
            effective_window_remaining_tokens
            - request_input_estimated_tokens
            - self.provider_profile.output_safety_gap_tokens,
        )
        request_output_cap_tokens = _request_output_cap_tokens(
            remaining_after_estimated_input_tokens=(
                remaining_after_estimated_input_tokens
            ),
            provider_default_completion_tokens=(
                self.provider_profile.provider_default_completion_tokens
            ),
            model_max_output_tokens=self.model_profile.max_output_tokens,
        )
        effective_output_cap_tokens = (
            request_output_cap_tokens
            if request_output_cap_tokens is not None
            else planned_output_reserve_tokens
        )

        return LlmPhaseTokenBudget(
            provider=self.provider_profile.provider_id,
            model_ref=self.model_profile.model_id.value,
            model_tpm_limit=model_tpm_limit,
            model_char_to_token_multiplier=(
                self.model_profile.model_char_to_token_multiplier
            ),
            prompt_id=self.prompt_profile.prompt_id,
            prompt_version=self.prompt_profile.prompt_version,
            prompt_tokens=prompt_tokens,
            phase=self.operation_profile.phase,
            operation=self.operation_profile.operation,
            input_artifact_kind=self.operation_profile.input_artifact_kind,
            output_artifact_kind=self.operation_profile.output_artifact_kind,
            request_safety_gap_tokens=request_safety_gap_tokens,
            output_safety_gap_tokens=(self.provider_profile.output_safety_gap_tokens),
            provider_default_completion_tokens=(
                self.provider_profile.provider_default_completion_tokens
            ),
            artifact_token_estimate=artifact_token_estimate,
            capacity_window_remaining_tokens=effective_window_remaining_tokens,
            max_artifact_input_tokens=max_artifact_input_tokens,
            planned_output_reserve_tokens=planned_output_reserve_tokens,
            request_input_estimated_tokens=request_input_estimated_tokens,
            remaining_after_estimated_input_tokens=(
                remaining_after_estimated_input_tokens
            ),
            effective_output_cap_tokens=effective_output_cap_tokens,
            request_output_cap_tokens=request_output_cap_tokens,
            reserved_total_tokens=(
                request_input_estimated_tokens + effective_output_cap_tokens
            ),
        )

    def calculate_for_artifact_chars(
        self,
        char_count: int,
        *,
        capacity_window_remaining_tokens: int | None = None,
    ) -> LlmPhaseTokenBudget:
        return self.calculate_for_artifact_tokens(
            self.estimate_artifact_tokens_from_chars(char_count),
            capacity_window_remaining_tokens=capacity_window_remaining_tokens,
        )


def _validate_profile_contract(
    *,
    provider_profile: ProviderBudgetProfile,
    model_profile: ModelProfile,
    prompt_profile: PromptProfile,
    operation_profile: LlmPhaseOperationProfile,
) -> None:
    provider_id = provider_profile.provider_id
    model_provider_id = model_profile.provider_id.value
    if provider_id != model_provider_id:
        raise ValueError("provider profile must match model provider_id")
    if prompt_profile.provider_id != provider_id:
        raise ValueError("prompt profile must match provider profile")
    if operation_profile.provider_id != provider_id:
        raise ValueError("operation profile must match provider profile")
    if prompt_profile.model_ref != model_profile.model_id.value:
        raise ValueError("prompt profile must match model profile")
    if operation_profile.primary_model_ref != model_profile.model_id.value:
        raise ValueError("operation primary model must match model profile")
    if operation_profile.prompt_id != prompt_profile.prompt_id:
        raise ValueError("operation prompt_id must match prompt profile")
    if operation_profile.prompt_version != prompt_profile.prompt_version:
        raise ValueError("operation prompt_version must match prompt profile")


def _model_tpm_limit(model_profile: ModelProfile) -> int:
    tokens_per_minute = model_profile.rate_limits.tokens_per_minute
    if (
        isinstance(tokens_per_minute, bool)
        or not isinstance(tokens_per_minute, int)
        or tokens_per_minute <= 0
    ):
        raise ValueError("model rate_limits.tokens_per_minute must be positive int")
    return tokens_per_minute


def _request_output_cap_tokens(
    *,
    remaining_after_estimated_input_tokens: int,
    provider_default_completion_tokens: int,
    model_max_output_tokens: int,
) -> int | None:
    if remaining_after_estimated_input_tokens <= provider_default_completion_tokens:
        return None
    return min(remaining_after_estimated_input_tokens, model_max_output_tokens)


def model_profile_by_ref(
    model_profiles: tuple[ModelProfile, ...],
    model_ref: str,
) -> ModelProfile:
    for model_profile in model_profiles:
        if model_profile.model_id.value == model_ref:
            return model_profile
    raise ValueError(f"model profile not found: {model_ref}")


def json_safe_capacity_estimate(
    payload: Mapping[str, object],
) -> dict[str, object]:
    return dict(payload)
