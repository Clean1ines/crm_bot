from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


class LlmDispatchInputSizePreflightDecision(StrEnum):
    USE_ACTIVE_MODEL = "USE_ACTIVE_MODEL"
    USE_LARGER_INPUT_MODEL = "USE_LARGER_INPUT_MODEL"
    SOURCE_SPLIT_REQUIRED = "SOURCE_SPLIT_REQUIRED"


@dataclass(frozen=True, slots=True)
class ResolveLlmDispatchInputSizePreflightCommand:
    active_model_ref: str
    profile: LlmTaskCapacityProfile
    route_catalog: LlmModelRouteCatalog
    allow_automatic_fallbacks: bool = True

    def __post_init__(self) -> None:
        _require_non_empty_text(self.active_model_ref, field_name="active_model_ref")
        if not isinstance(self.profile, LlmTaskCapacityProfile):
            raise TypeError("profile must be LlmTaskCapacityProfile")
        if not isinstance(self.route_catalog, LlmModelRouteCatalog):
            raise TypeError("route_catalog must be LlmModelRouteCatalog")
        if not isinstance(self.allow_automatic_fallbacks, bool):
            raise TypeError("allow_automatic_fallbacks must be bool")


@dataclass(frozen=True, slots=True)
class ResolveLlmDispatchInputSizePreflightResult:
    decision: LlmDispatchInputSizePreflightDecision
    active_model_ref: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision, LlmDispatchInputSizePreflightDecision):
            raise TypeError("decision must be LlmDispatchInputSizePreflightDecision")
        _require_non_empty_text(self.active_model_ref, field_name="active_model_ref")
        _require_non_empty_text(self.reason, field_name="reason")


class ResolveLlmDispatchInputSizePreflight:
    def execute(
        self,
        command: ResolveLlmDispatchInputSizePreflightCommand,
    ) -> ResolveLlmDispatchInputSizePreflightResult:
        estimated_input_tokens = command.profile.estimated_input_tokens
        active_limits = command.route_catalog.capacity_limits_for_model_ref(
            command.active_model_ref,
        )

        if estimated_input_tokens <= active_limits.input_token_limit:
            return ResolveLlmDispatchInputSizePreflightResult(
                decision=LlmDispatchInputSizePreflightDecision.USE_ACTIVE_MODEL,
                active_model_ref=command.active_model_ref,
                reason="estimated input tokens fit active model input limit",
            )

        fallback_model_ref = None
        if command.allow_automatic_fallbacks:
            fallback_model_ref = _first_fallback_that_fits_input(
                estimated_input_tokens=estimated_input_tokens,
                current_model_ref=command.active_model_ref,
                route_catalog=command.route_catalog,
            )
        if fallback_model_ref is not None:
            return ResolveLlmDispatchInputSizePreflightResult(
                decision=LlmDispatchInputSizePreflightDecision.USE_LARGER_INPUT_MODEL,
                active_model_ref=fallback_model_ref,
                reason=(
                    "estimated input tokens exceed active model input limit; "
                    "selected larger input model"
                ),
            )

        return ResolveLlmDispatchInputSizePreflightResult(
            decision=LlmDispatchInputSizePreflightDecision.SOURCE_SPLIT_REQUIRED,
            active_model_ref=command.active_model_ref,
            reason="estimated input tokens exceed all automatic fallback input limits",
        )


def _first_fallback_that_fits_input(
    *,
    estimated_input_tokens: int,
    current_model_ref: str,
    route_catalog: LlmModelRouteCatalog,
) -> str | None:
    for (
        model_ref
    ) in route_catalog.automatic_fallback_model_refs_with_larger_input_limit(
        current_model_ref,
    ):
        limits = route_catalog.capacity_limits_for_model_ref(model_ref)
        if estimated_input_tokens <= limits.input_token_limit:
            return model_ref
    return None


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
