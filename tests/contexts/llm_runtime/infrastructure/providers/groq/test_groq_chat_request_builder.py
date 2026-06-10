from __future__ import annotations

from decimal import Decimal

import pytest

from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelExecutionSettings,
    default_groq_llm_model_route_catalog,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.model_lifecycle import ModelLifecycle
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.rate_limit_profile import (
    RateLimitProfile,
)
from src.contexts.llm_runtime.domain.value_objects.reasoning_effort import (
    ReasoningEffort,
)
from src.contexts.llm_runtime.domain.value_objects.reasoning_profile import (
    ReasoningProfile,
)
from src.contexts.llm_runtime.domain.value_objects.token_price import TokenPrice
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    GroqChatMessage,
    GroqChatMessageRole,
    GroqChatRequestBuilder,
    GroqChatRequestOptions,
    GroqResponseFormatKind,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
)


def _provider_id() -> ProviderId:
    return ProviderId("groq")


def _route(model: str = "qwen/qwen3-32b") -> LlmRoute:
    return LlmRoute(
        provider_id=_provider_id(),
        model_id=ModelId(model),
        account_ref=ProviderAccountRef("groq_org_primary"),
    )


def _message() -> GroqChatMessage:
    return GroqChatMessage(
        role=GroqChatMessageRole.USER,
        content="Return JSON.",
    )


def _custom_profile(
    *,
    supports_json_object: bool = True,
    reasoning_profile: ReasoningProfile | None = None,
) -> ModelProfile:
    return ModelProfile(
        provider_id=_provider_id(),
        model_id=ModelId("custom-model"),
        lifecycle=ModelLifecycle.PRODUCTION,
        context_window_tokens=8_000,
        max_output_tokens=4_000,
        model_rank=0,
        rate_limits=RateLimitProfile(),
        token_price=TokenPrice(
            input_per_million=Decimal("0"),
            output_per_million=Decimal("0"),
        ),
        reasoning_profile=reasoning_profile or ReasoningProfile.unsupported(),
        supports_json_object=supports_json_object,
    )


def test_builder_creates_chat_completion_payload_with_json_mode() -> None:
    qwen_profile = build_groq_free_plan_model_profiles()[0]

    request = GroqChatRequestBuilder().build(
        route=_route(),
        model_profile=qwen_profile,
        messages=(
            GroqChatMessage(
                role=GroqChatMessageRole.SYSTEM, content="You return JSON."
            ),
            _message(),
        ),
    )

    assert request.payload["model"] == "qwen/qwen3-32b"
    assert request.payload["messages"] == [
        {"role": "system", "content": "You return JSON."},
        {"role": "user", "content": "Return JSON."},
    ]
    assert request.payload["response_format"] == {"type": "json_object"}
    assert request.payload["max_completion_tokens"] == 40_960
    assert request.payload["temperature"] == 0.0


def test_qwen_default_reasoning_effort_is_none_to_preserve_output_budget() -> None:
    qwen_profile = build_groq_free_plan_model_profiles()[0]

    request = GroqChatRequestBuilder().build(
        route=_route(),
        model_profile=qwen_profile,
        messages=(_message(),),
    )

    assert request.payload["reasoning_effort"] == "none"


def test_disabled_execution_settings_suppress_model_default_reasoning() -> None:
    qwen_profile = build_groq_free_plan_model_profiles()[0]

    request = GroqChatRequestBuilder().build(
        route=_route(),
        model_profile=qwen_profile,
        messages=(_message(),),
        options=GroqChatRequestOptions(
            execution_settings=LlmModelExecutionSettings(reasoning_enabled=False),
        ),
    )

    assert "reasoning_effort" not in request.payload


def test_qwen_default_catalog_settings_suppress_reasoning() -> None:
    qwen_profile = build_groq_free_plan_model_profiles()[0]
    settings = default_groq_llm_model_route_catalog().execution_settings_for_model_ref(
        "qwen/qwen3-32b",
    )

    request = GroqChatRequestBuilder().build(
        route=_route(),
        model_profile=qwen_profile,
        messages=(_message(),),
        options=GroqChatRequestOptions(execution_settings=settings),
    )

    assert "reasoning_effort" not in request.payload


def test_execution_settings_enabled_uses_explicit_reasoning_effort() -> None:
    gpt_oss_profile = build_groq_free_plan_model_profiles()[2]

    request = GroqChatRequestBuilder().build(
        route=_route(model="openai/gpt-oss-20b"),
        model_profile=gpt_oss_profile,
        messages=(_message(),),
        options=GroqChatRequestOptions(
            execution_settings=LlmModelExecutionSettings(
                reasoning_enabled=True,
                reasoning_effort="low",
            ),
        ),
    )

    assert request.payload["reasoning_effort"] == "low"


def test_options_reasoning_effort_overrides_execution_settings_reasoning_effort() -> (
    None
):
    gpt_oss_profile = build_groq_free_plan_model_profiles()[2]

    request = GroqChatRequestBuilder().build(
        route=_route(model="openai/gpt-oss-20b"),
        model_profile=gpt_oss_profile,
        messages=(_message(),),
        options=GroqChatRequestOptions(
            reasoning_effort=ReasoningEffort.HIGH,
            execution_settings=LlmModelExecutionSettings(
                reasoning_enabled=True,
                reasoning_effort="low",
            ),
        ),
    )

    assert request.payload["reasoning_effort"] == "high"


def test_options_reject_invalid_execution_settings_type() -> None:
    kwargs = {"execution_settings": object()}

    with pytest.raises(TypeError, match="execution_settings"):
        GroqChatRequestOptions(**kwargs)


def test_explicit_reasoning_effort_must_be_supported_by_model() -> None:
    qwen_profile = build_groq_free_plan_model_profiles()[0]

    allowed = GroqChatRequestBuilder().build(
        route=_route(),
        model_profile=qwen_profile,
        messages=(_message(),),
        options=GroqChatRequestOptions(reasoning_effort=ReasoningEffort.DEFAULT),
    )

    assert allowed.payload["reasoning_effort"] == "default"

    with pytest.raises(ValueError):
        GroqChatRequestBuilder().build(
            route=_route(),
            model_profile=qwen_profile,
            messages=(_message(),),
            options=GroqChatRequestOptions(reasoning_effort=ReasoningEffort.HIGH),
        )


def test_reasoning_effort_is_omitted_for_models_without_reasoning_controls() -> None:
    llama_profile = build_groq_free_plan_model_profiles()[1]

    request = GroqChatRequestBuilder().build(
        route=_route(model="llama-3.1-8b-instant"),
        model_profile=llama_profile,
        messages=(_message(),),
    )

    assert "reasoning_effort" not in request.payload


def test_builder_validates_route_matches_model_profile() -> None:
    qwen_profile = build_groq_free_plan_model_profiles()[0]

    with pytest.raises(ValueError):
        GroqChatRequestBuilder().build(
            route=_route(model="llama-3.1-8b-instant"),
            model_profile=qwen_profile,
            messages=(_message(),),
        )


def test_builder_rejects_max_completion_tokens_above_model_limit() -> None:
    qwen_profile = build_groq_free_plan_model_profiles()[0]

    with pytest.raises(ValueError):
        GroqChatRequestBuilder().build(
            route=_route(),
            model_profile=qwen_profile,
            messages=(_message(),),
            options=GroqChatRequestOptions(max_completion_tokens=40_961),
        )


def test_builder_can_emit_text_mode_without_response_format() -> None:
    qwen_profile = build_groq_free_plan_model_profiles()[0]

    request = GroqChatRequestBuilder().build(
        route=_route(),
        model_profile=qwen_profile,
        messages=(_message(),),
        options=GroqChatRequestOptions(response_format=GroqResponseFormatKind.TEXT),
    )

    assert "response_format" not in request.payload


def test_builder_rejects_json_mode_when_model_does_not_support_it() -> None:
    profile = _custom_profile(supports_json_object=False)

    with pytest.raises(ValueError):
        GroqChatRequestBuilder().build(
            route=LlmRoute(
                provider_id=_provider_id(),
                model_id=ModelId("custom-model"),
                account_ref=ProviderAccountRef("groq_org_primary"),
            ),
            model_profile=profile,
            messages=(_message(),),
        )


def test_message_and_options_validate_input() -> None:
    with pytest.raises(ValueError):
        GroqChatMessage(role=GroqChatMessageRole.USER, content="")

    with pytest.raises(ValueError):
        GroqChatRequestOptions(max_completion_tokens=0)

    with pytest.raises(ValueError):
        GroqChatRequestOptions(temperature=3)
