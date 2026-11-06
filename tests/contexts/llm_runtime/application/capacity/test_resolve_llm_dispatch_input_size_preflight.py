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


def _profile(prompt_tokens: int) -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a",
        estimated_prompt_tokens=prompt_tokens,
        estimated_completion_tokens=500,
    )


def _execute(
    *,
    active_model_ref: str = "openai/gpt-oss-120b",
    estimated_prompt_tokens: int,
):
    return ResolveLlmDispatchInputSizePreflight().execute(
        ResolveLlmDispatchInputSizePreflightCommand(
            active_model_ref=active_model_ref,
            profile=_profile(estimated_prompt_tokens),
            route_catalog=default_groq_llm_model_route_catalog(),
        )
    )


def test_estimated_prompt_fits_active_model_uses_active_model() -> None:
    result = _execute(estimated_prompt_tokens=3000)

    assert result.decision is LlmDispatchInputSizePreflightDecision.USE_ACTIVE_MODEL
    assert result.active_model_ref == "openai/gpt-oss-120b"
    assert result.reason == "estimated prompt tokens fit active model input limit"


def test_estimated_prompt_within_primary_capacity_uses_active_model() -> None:
    result = _execute(estimated_prompt_tokens=9000)

    assert result.decision is LlmDispatchInputSizePreflightDecision.USE_ACTIVE_MODEL
    assert result.active_model_ref == "openai/gpt-oss-120b"


def test_prompt_just_above_primary_limit_requires_source_split() -> None:
    result = _execute(estimated_prompt_tokens=131_073)

    assert (
        result.decision is LlmDispatchInputSizePreflightDecision.SOURCE_SPLIT_REQUIRED
    )
    assert result.active_model_ref == "openai/gpt-oss-120b"


def test_estimated_prompt_exceeds_all_routes_requires_source_split() -> None:
    result = _execute(estimated_prompt_tokens=200000)

    assert (
        result.decision is LlmDispatchInputSizePreflightDecision.SOURCE_SPLIT_REQUIRED
    )
    assert result.active_model_ref == "openai/gpt-oss-120b"
    assert result.reason == (
        "estimated prompt tokens exceed all automatic fallback input limits"
    )


def test_automatic_fallback_can_be_disabled_for_phase_specific_routing() -> None:
    result = ResolveLlmDispatchInputSizePreflight().execute(
        ResolveLlmDispatchInputSizePreflightCommand(
            active_model_ref="openai/gpt-oss-120b",
            profile=_profile(131_073),
            route_catalog=default_groq_llm_model_route_catalog(),
            allow_automatic_fallbacks=False,
        )
    )

    assert (
        result.decision is LlmDispatchInputSizePreflightDecision.SOURCE_SPLIT_REQUIRED
    )
    assert result.active_model_ref == "openai/gpt-oss-120b"
