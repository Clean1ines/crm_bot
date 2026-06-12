from __future__ import annotations

import pytest

from src.contexts.llm_runtime.application.capacity.resolve_llm_dispatch_preparation_strategy import (
    ResolveLlmDispatchPreparationStrategy,
    ResolveLlmDispatchPreparationStrategyCommand,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
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


def _command(strategy: str | None):
    return ResolveLlmDispatchPreparationStrategyCommand(
        current_active_model_ref=_primary_model_ref(),
        strategy=strategy,
        route_catalog=_catalog(),
    )


def test_no_strategy_keeps_active_model_ref() -> None:
    result = _resolver().execute(_command(None))

    assert result.active_model_ref == _primary_model_ref()
    assert result.strategy_applied is None


def test_retry_same_model_keeps_active_model_ref() -> None:
    result = _resolver().execute(_command("RETRY_SAME_MODEL"))

    assert result.active_model_ref == _primary_model_ref()
    assert result.strategy_applied == "RETRY_SAME_MODEL"


def test_same_model_marker_keeps_active_model_ref() -> None:
    result = _resolver().execute(_command("SAME_MODEL"))

    assert result.active_model_ref == _primary_model_ref()
    assert result.strategy_applied == "SAME_MODEL"


def test_retry_fallback_model_resolves_first_automatic_fallback_model() -> None:
    catalog = _catalog()

    result = _resolver().execute(_command("RETRY_FALLBACK_MODEL"))

    assert result.active_model_ref == catalog.automatic_fallback_model_refs()[0]
    assert result.strategy_applied == "RETRY_FALLBACK_MODEL"


def test_fallback_required_marker_resolves_first_automatic_fallback_model() -> None:
    catalog = _catalog()

    result = _resolver().execute(_command("FALLBACK_MODEL_REQUIRED"))

    assert result.active_model_ref == catalog.automatic_fallback_model_refs()[0]
    assert result.strategy_applied == "FALLBACK_MODEL_REQUIRED"


def test_retry_larger_output_limit_uses_automatic_fallback_for_now() -> None:
    catalog = _catalog()

    result = _resolver().execute(_command("RETRY_LARGER_OUTPUT_LIMIT_MODEL"))

    assert result.active_model_ref == catalog.automatic_fallback_model_refs()[0]
    assert result.strategy_applied == "RETRY_LARGER_OUTPUT_LIMIT_MODEL"


def test_larger_output_required_marker_uses_automatic_fallback_for_now() -> None:
    catalog = _catalog()

    result = _resolver().execute(_command("LARGER_OUTPUT_LIMIT_MODEL_REQUIRED"))

    assert result.active_model_ref == catalog.automatic_fallback_model_refs()[0]
    assert result.strategy_applied == "LARGER_OUTPUT_LIMIT_MODEL_REQUIRED"


def test_unknown_strategy_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown llm dispatch preparation strategy"):
        _resolver().execute(_command("NO_SUCH_STRATEGY"))


def test_fallback_strategy_without_automatic_fallback_raises() -> None:
    catalog = LlmModelRouteCatalog(
        routes=(
            LlmModelRoute(
                model_ref="primary-model",
                role=LlmModelRouteRole.PRIMARY,
                order=0,
                execution_settings=LlmModelExecutionSettings(reasoning_enabled=False),
            ),
            LlmModelRoute(
                model_ref="degraded-model",
                role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                order=1,
                execution_settings=LlmModelExecutionSettings(reasoning_enabled=False),
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
