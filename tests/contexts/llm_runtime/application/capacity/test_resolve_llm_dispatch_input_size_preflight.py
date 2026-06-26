from __future__ import annotations

from src.contexts.llm_runtime.application.capacity.resolve_llm_dispatch_input_size_preflight import (
    LlmDispatchInputSizePreflightDecision,
    ResolveLlmDispatchInputSizePreflight,
    ResolveLlmDispatchInputSizePreflightCommand,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


def _profile(input_tokens: int) -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a",
        input_tokens=input_tokens,
        artifact_tokens=500,
    )


def _execute(
    *,
    active_model_ref: str = "qwen/qwen3-32b",
    estimated_input_tokens: int,
):
    return ResolveLlmDispatchInputSizePreflight().execute(
        ResolveLlmDispatchInputSizePreflightCommand(
            active_model_ref=active_model_ref,
            profile=_profile(estimated_input_tokens),
            route_catalog=default_groq_llm_model_route_catalog(),
        )
    )


def test_estimated_input_fits_active_model_uses_active_model() -> None:
    result = _execute(estimated_input_tokens=3000)

    assert result.decision is LlmDispatchInputSizePreflightDecision.USE_ACTIVE_MODEL
    assert result.active_model_ref == "qwen/qwen3-32b"
    assert result.reason == "estimated input tokens fit active model input limit"


def test_estimated_input_exceeds_active_but_fits_fallback_uses_larger_input_model() -> (
    None
):
    result = _execute(estimated_input_tokens=7000)

    assert (
        result.decision is LlmDispatchInputSizePreflightDecision.USE_LARGER_INPUT_MODEL
    )
    assert result.active_model_ref == "llama-3.3-70b-versatile"


def test_chosen_fallback_must_fit_estimated_input_tokens() -> None:
    result = _execute(estimated_input_tokens=20_000)

    assert (
        result.decision is LlmDispatchInputSizePreflightDecision.USE_LARGER_INPUT_MODEL
    )
    assert result.active_model_ref == "meta-llama/llama-4-scout-17b-16e-instruct"


def test_estimated_input_exceeds_all_routes_requires_source_split() -> None:
    result = _execute(estimated_input_tokens=200000)

    assert (
        result.decision is LlmDispatchInputSizePreflightDecision.SOURCE_SPLIT_REQUIRED
    )
    assert result.active_model_ref == "qwen/qwen3-32b"
    assert result.reason == (
        "estimated input tokens exceed all automatic fallback input limits"
    )


def test_automatic_fallback_can_be_disabled_for_phase_specific_routing() -> None:
    result = ResolveLlmDispatchInputSizePreflight().execute(
        ResolveLlmDispatchInputSizePreflightCommand(
            active_model_ref="qwen/qwen3-32b",
            profile=_profile(7000),
            route_catalog=default_groq_llm_model_route_catalog(),
            allow_automatic_fallbacks=False,
        )
    )

    assert (
        result.decision is LlmDispatchInputSizePreflightDecision.SOURCE_SPLIT_REQUIRED
    )
    assert result.active_model_ref == "qwen/qwen3-32b"
