import pytest

from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelCapacityLimits,
    LlmModelExecutionSettings,
    LlmModelRoute,
    LlmModelRouteCatalog,
    LlmModelRouteRole,
    default_groq_llm_model_route_catalog,
)


def _settings() -> LlmModelExecutionSettings:
    return LlmModelExecutionSettings(reasoning_enabled=False)


def _limits(
    *,
    input_token_limit: int = 32768,
    output_token_limit: int = 8192,
) -> LlmModelCapacityLimits:
    return LlmModelCapacityLimits(
        input_token_limit=input_token_limit,
        output_token_limit=output_token_limit,
    )


def _route(
    *,
    model_ref: str,
    role: LlmModelRouteRole,
    order: int,
    input_token_limit: int = 32768,
    output_token_limit: int = 8192,
) -> LlmModelRoute:
    return LlmModelRoute(
        model_ref=model_ref,
        role=role,
        order=order,
        execution_settings=_settings(),
        capacity_limits=_limits(
            input_token_limit=input_token_limit,
            output_token_limit=output_token_limit,
        ),
    )


def test_default_catalog_primary_is_qwen() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.primary_model_ref() == "qwen/qwen3-32b"


def test_default_catalog_automatic_fallback_refs_are_ordered() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.automatic_fallback_model_refs() == (
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-120b",
    )


def test_default_catalog_degraded_user_choice_model() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.degraded_user_choice_model_ref() == "llama-3.1-8b-instant"


def test_route_for_model_ref_returns_role_and_order() -> None:
    catalog = default_groq_llm_model_route_catalog()

    route = catalog.route_for_model_ref("openai/gpt-oss-120b")

    assert route is not None
    assert route.role is LlmModelRouteRole.AUTOMATIC_FALLBACK
    assert route.order == 3


def test_model_route_requires_capacity_limits() -> None:
    with pytest.raises(TypeError, match="capacity_limits"):
        LlmModelRoute(
            model_ref="qwen/qwen3-32b",
            role=LlmModelRouteRole.PRIMARY,
            order=0,
            execution_settings=_settings(),
            capacity_limits=object(),
        )


def test_capacity_limits_reject_non_int_input_limit() -> None:
    with pytest.raises(TypeError, match="input_token_limit must be int"):
        LlmModelCapacityLimits(
            input_token_limit=True,
            output_token_limit=8192,
        )


def test_capacity_limits_reject_non_positive_output_limit() -> None:
    with pytest.raises(ValueError, match="output_token_limit must be positive"):
        LlmModelCapacityLimits(
            input_token_limit=32768,
            output_token_limit=0,
        )


def test_catalog_returns_capacity_limits_by_model_ref() -> None:
    catalog = default_groq_llm_model_route_catalog()

    limits = catalog.capacity_limits_for_model_ref("openai/gpt-oss-120b")

    assert limits.input_token_limit == 8_000
    assert limits.output_token_limit == 65_536


def test_capacity_limits_for_model_ref_rejects_unknown_model() -> None:
    catalog = default_groq_llm_model_route_catalog()

    with pytest.raises(ValueError, match="model_ref is not in route catalog"):
        catalog.capacity_limits_for_model_ref("unknown/model")


def test_larger_output_fallback_returns_only_larger_output_models_by_order() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.automatic_fallback_model_refs_with_larger_output_limit(
        "qwen/qwen3-32b",
    ) == (
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-120b",
    )


def test_larger_input_fallback_returns_only_larger_input_models_by_order() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.automatic_fallback_model_refs_with_larger_input_limit(
        "qwen/qwen3-32b",
    ) == (
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-120b",
    )


def test_rejects_duplicate_model_ref() -> None:
    with pytest.raises(ValueError, match="unique model_ref"):
        LlmModelRouteCatalog(
            routes=(
                _route(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=0,
                ),
                _route(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=1,
                ),
            ),
        )


def test_rejects_duplicate_primary_role() -> None:
    with pytest.raises(ValueError, match="exactly one PRIMARY"):
        LlmModelRouteCatalog(
            routes=(
                _route(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=0,
                ),
                _route(
                    model_ref="openai/gpt-oss-120b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=1,
                ),
                _route(
                    model_ref="llama-3.1-8b-instant",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=2,
                ),
            ),
        )


def test_rejects_duplicate_degraded_user_choice_role() -> None:
    with pytest.raises(ValueError, match="exactly one DEGRADED_USER_CHOICE"):
        LlmModelRouteCatalog(
            routes=(
                _route(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=0,
                ),
                _route(
                    model_ref="llama-3.1-8b-instant",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=1,
                ),
                _route(
                    model_ref="llama-3.1-8b-alt",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=2,
                ),
            ),
        )


def test_rejects_duplicate_order() -> None:
    with pytest.raises(ValueError, match="unique order"):
        LlmModelRouteCatalog(
            routes=(
                _route(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=0,
                ),
                _route(
                    model_ref="llama-3.1-8b-instant",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=0,
                ),
            ),
        )


def test_qwen_primary_route_disables_reasoning() -> None:
    catalog = default_groq_llm_model_route_catalog()

    settings = catalog.execution_settings_for_model_ref("qwen/qwen3-32b")

    assert settings.reasoning_enabled is False
    assert settings.reasoning_effort is None


def test_qwen_execution_settings_provider_options_disable_reasoning() -> None:
    catalog = default_groq_llm_model_route_catalog()

    settings = catalog.execution_settings_for_model_ref("qwen/qwen3-32b")

    assert settings.to_provider_options() == {"reasoning_enabled": False}


def test_reasoning_effort_is_rejected_when_reasoning_disabled() -> None:
    with pytest.raises(
        ValueError,
        match="reasoning_effort must be None when reasoning_enabled is False",
    ):
        LlmModelExecutionSettings(
            reasoning_enabled=False,
            reasoning_effort="low",
        )


def test_execution_settings_for_model_ref_returns_known_model_settings() -> None:
    catalog = default_groq_llm_model_route_catalog()

    settings = catalog.execution_settings_for_model_ref("openai/gpt-oss-120b")

    assert isinstance(settings, LlmModelExecutionSettings)
    assert settings.reasoning_enabled is False


def test_execution_settings_for_model_ref_rejects_unknown_model() -> None:
    catalog = default_groq_llm_model_route_catalog()

    with pytest.raises(ValueError, match="model_ref is not in route catalog"):
        catalog.execution_settings_for_model_ref("unknown/model")


def test_every_default_catalog_route_has_explicit_execution_settings() -> None:
    catalog = default_groq_llm_model_route_catalog()

    for route in catalog.routes:
        assert isinstance(route.execution_settings, LlmModelExecutionSettings)
        assert route.execution_settings.to_provider_options() == {
            "reasoning_enabled": False,
        }


def test_every_default_catalog_route_has_explicit_capacity_limits() -> None:
    catalog = default_groq_llm_model_route_catalog()

    for route in catalog.routes:
        assert isinstance(route.capacity_limits, LlmModelCapacityLimits)
        assert route.capacity_limits.input_token_limit > 0
        assert route.capacity_limits.output_token_limit > 0


def test_enabled_reasoning_provider_options_include_effort_when_present() -> None:
    settings = LlmModelExecutionSettings(
        reasoning_enabled=True,
        reasoning_effort="medium",
    )

    assert settings.to_provider_options() == {
        "reasoning_enabled": True,
        "reasoning_effort": "medium",
    }


def test_daily_limit_fallback_chain_excludes_openai_gpt_oss() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.automatic_fallback_model_refs()[0] == "llama-3.3-70b-versatile"
    assert catalog.automatic_fallback_model_refs_for_daily_limit()[0] == (
        "llama-3.3-70b-versatile"
    )
    assert "openai/gpt-oss-120b" not in (
        catalog.automatic_fallback_model_refs_for_daily_limit()
    )
