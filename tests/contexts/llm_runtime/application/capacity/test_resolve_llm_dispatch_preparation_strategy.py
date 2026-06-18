from __future__ import annotations

import pytest

from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.llm_runtime.application.capacity.resolve_llm_dispatch_preparation_strategy import (
    ResolveLlmDispatchPreparationStrategy,
    ResolveLlmDispatchPreparationStrategyCommand,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelCapacityLimits,
    LlmModelExecutionSettings,
    LlmModelRoute,
    LlmModelRouteCatalog,
    LlmModelRouteRole,
    default_groq_llm_model_route_catalog,
)


def _resolver() -> ResolveLlmDispatchPreparationStrategy:
    return ResolveLlmDispatchPreparationStrategy()


def _catalog() -> LlmModelRouteCatalog:
    return default_groq_llm_model_route_catalog()


def _primary_model_ref() -> str:
    return _catalog().primary_model_ref()


def _settings() -> LlmModelExecutionSettings:
    return LlmModelExecutionSettings(reasoning_enabled=False)


def _limits(
    *,
    input_token_limit: int,
    output_token_limit: int,
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
    input_token_limit: int,
    output_token_limit: int,
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


def _command(strategy: str | None):
    return ResolveLlmDispatchPreparationStrategyCommand(
        current_active_model_ref=_primary_model_ref(),
        strategy=strategy,
        route_catalog=_catalog(),
    )


def _retry_plan_command(retry_plan: WorkItemRetryPlan):
    return ResolveLlmDispatchPreparationStrategyCommand(
        current_active_model_ref=_primary_model_ref(),
        route_catalog=_catalog(),
        retry_plan=retry_plan,
    )


def test_no_strategy_keeps_active_model_ref() -> None:
    result = _resolver().execute(_command(None))

    assert result.active_model_ref == _primary_model_ref()
    assert result.strategy_applied is None


def test_retry_same_model_keeps_active_model_ref() -> None:
    result = _resolver().execute(_command("RETRY_SAME_MODEL"))

    assert result.active_model_ref == _primary_model_ref()
    assert result.strategy_applied == "RETRY_SAME_MODEL"


def test_retry_plan_same_model_keeps_active_model_ref() -> None:
    result = _resolver().execute(
        _retry_plan_command(WorkItemRetryPlan.RETRY_SAME_MODEL),
    )

    assert result.active_model_ref == _primary_model_ref()
    assert result.strategy_applied == WorkItemRetryPlan.RETRY_SAME_MODEL.value


def test_same_model_marker_keeps_active_model_ref() -> None:
    result = _resolver().execute(_command("SAME_MODEL"))

    assert result.active_model_ref == _primary_model_ref()
    assert result.strategy_applied == "SAME_MODEL"


def test_retry_empty_claims_check_model_resolves_first_automatic_fallback_model() -> (
    None
):
    catalog = _catalog()

    result = _resolver().execute(_command("RETRY_EMPTY_CLAIMS_CHECK_MODEL"))

    assert result.active_model_ref == catalog.automatic_fallback_model_refs()[0]
    assert result.strategy_applied == "RETRY_EMPTY_CLAIMS_CHECK_MODEL"


def test_retry_plan_empty_claims_check_resolves_first_automatic_fallback_model() -> (
    None
):
    catalog = _catalog()

    result = _resolver().execute(
        _retry_plan_command(WorkItemRetryPlan.RETRY_SPECIAL_EMPTY_CLAIMS_CHECK_MODEL),
    )

    assert result.active_model_ref == catalog.automatic_fallback_model_refs()[0]
    assert result.strategy_applied == (
        WorkItemRetryPlan.RETRY_SPECIAL_EMPTY_CLAIMS_CHECK_MODEL.value
    )


def test_empty_claims_check_required_marker_resolves_first_automatic_fallback_model() -> (
    None
):
    catalog = _catalog()

    result = _resolver().execute(_command("EMPTY_CLAIMS_CHECK_MODEL_REQUIRED"))

    assert result.active_model_ref == catalog.automatic_fallback_model_refs()[0]
    assert result.strategy_applied == "EMPTY_CLAIMS_CHECK_MODEL_REQUIRED"


def test_retry_fallback_model_marker_is_rejected_as_generic_retry_route() -> None:
    with pytest.raises(ValueError, match="RETRY_FALLBACK_MODEL"):
        _resolver().execute(_command("RETRY_FALLBACK_MODEL"))


def test_fallback_required_marker_resolves_first_automatic_fallback_model() -> None:
    catalog = _catalog()

    result = _resolver().execute(_command("FALLBACK_MODEL_REQUIRED"))

    assert result.active_model_ref == catalog.automatic_fallback_model_refs()[0]
    assert result.strategy_applied == "FALLBACK_MODEL_REQUIRED"


def test_retry_larger_output_limit_picks_first_larger_output_fallback() -> None:
    result = _resolver().execute(_command("RETRY_LARGER_OUTPUT_LIMIT_MODEL"))

    assert result.active_model_ref == "openai/gpt-oss-120b"
    assert result.strategy_applied == "RETRY_LARGER_OUTPUT_LIMIT_MODEL"


def test_larger_output_required_marker_picks_first_larger_output_fallback() -> None:
    result = _resolver().execute(_command("LARGER_OUTPUT_LIMIT_MODEL_REQUIRED"))

    assert result.active_model_ref == "openai/gpt-oss-120b"
    assert result.strategy_applied == "LARGER_OUTPUT_LIMIT_MODEL_REQUIRED"


def test_retry_larger_input_limit_picks_first_larger_input_fallback() -> None:
    result = _resolver().execute(_command("RETRY_LARGER_INPUT_LIMIT_MODEL"))

    assert result.active_model_ref == "openai/gpt-oss-120b"
    assert result.strategy_applied == "RETRY_LARGER_INPUT_LIMIT_MODEL"


def test_larger_input_required_marker_picks_first_larger_input_fallback() -> None:
    result = _resolver().execute(_command("LARGER_INPUT_LIMIT_MODEL_REQUIRED"))

    assert result.active_model_ref == "openai/gpt-oss-120b"
    assert result.strategy_applied == "LARGER_INPUT_LIMIT_MODEL_REQUIRED"


def test_larger_output_strategy_skips_first_fallback_without_larger_output() -> None:
    catalog = LlmModelRouteCatalog(
        routes=(
            _route(
                model_ref="primary-model",
                role=LlmModelRouteRole.PRIMARY,
                order=0,
                input_token_limit=32768,
                output_token_limit=8192,
            ),
            _route(
                model_ref="fallback-same-output",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=1,
                input_token_limit=131072,
                output_token_limit=8192,
            ),
            _route(
                model_ref="fallback-larger-output",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=2,
                input_token_limit=32768,
                output_token_limit=16384,
            ),
            _route(
                model_ref="degraded-model",
                role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                order=3,
                input_token_limit=8192,
                output_token_limit=4096,
            ),
        )
    )

    result = _resolver().execute(
        ResolveLlmDispatchPreparationStrategyCommand(
            current_active_model_ref="primary-model",
            strategy="RETRY_LARGER_OUTPUT_LIMIT_MODEL",
            route_catalog=catalog,
        )
    )

    assert result.active_model_ref == "fallback-larger-output"


def test_unknown_strategy_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown llm dispatch preparation strategy"):
        _resolver().execute(_command("NO_SUCH_STRATEGY"))


def test_fallback_strategy_without_automatic_fallback_raises() -> None:
    catalog = LlmModelRouteCatalog(
        routes=(
            _route(
                model_ref="primary-model",
                role=LlmModelRouteRole.PRIMARY,
                order=0,
                input_token_limit=32768,
                output_token_limit=8192,
            ),
            _route(
                model_ref="degraded-model",
                role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                order=1,
                input_token_limit=8192,
                output_token_limit=4096,
            ),
        )
    )

    with pytest.raises(ValueError, match="no automatic fallback"):
        _resolver().execute(
            ResolveLlmDispatchPreparationStrategyCommand(
                current_active_model_ref="primary-model",
                strategy="FALLBACK_MODEL_REQUIRED",
                route_catalog=catalog,
            )
        )


def test_larger_output_strategy_without_larger_output_fallback_raises() -> None:
    catalog = LlmModelRouteCatalog(
        routes=(
            _route(
                model_ref="primary-model",
                role=LlmModelRouteRole.PRIMARY,
                order=0,
                input_token_limit=32768,
                output_token_limit=8192,
            ),
            _route(
                model_ref="fallback-same-output",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=1,
                input_token_limit=131072,
                output_token_limit=8192,
            ),
            _route(
                model_ref="degraded-model",
                role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                order=2,
                input_token_limit=8192,
                output_token_limit=4096,
            ),
        )
    )

    with pytest.raises(ValueError, match="larger output limit"):
        _resolver().execute(
            ResolveLlmDispatchPreparationStrategyCommand(
                current_active_model_ref="primary-model",
                strategy="RETRY_LARGER_OUTPUT_LIMIT_MODEL",
                route_catalog=catalog,
            )
        )


def test_daily_limit_fallback_skips_openai_gpt_oss() -> None:
    result = ResolveLlmDispatchPreparationStrategy().execute(
        ResolveLlmDispatchPreparationStrategyCommand(
            current_active_model_ref="qwen/qwen3-32b",
            strategy="DAILY_LIMIT_FALLBACK_MODEL_REQUIRED",
            route_catalog=default_groq_llm_model_route_catalog(),
        )
    )

    assert result.active_model_ref == "llama-3.3-70b-versatile"
    assert result.strategy_applied == "DAILY_LIMIT_FALLBACK_MODEL_REQUIRED"


def test_retry_plan_daily_limit_fallback_skips_openai_gpt_oss() -> None:
    result = ResolveLlmDispatchPreparationStrategy().execute(
        ResolveLlmDispatchPreparationStrategyCommand(
            current_active_model_ref="qwen/qwen3-32b",
            route_catalog=default_groq_llm_model_route_catalog(),
            retry_plan=WorkItemRetryPlan.RETRY_DAILY_FALLBACK_MODEL,
        )
    )

    assert result.active_model_ref == "llama-3.3-70b-versatile"
    assert result.strategy_applied == WorkItemRetryPlan.RETRY_DAILY_FALLBACK_MODEL.value
