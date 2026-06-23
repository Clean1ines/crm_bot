from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)


@dataclass(frozen=True, slots=True)
class ResolveLlmDispatchPreparationStrategyCommand:
    current_active_model_ref: str
    route_catalog: LlmModelRouteCatalog
    retry_plan: WorkItemRetryPlan | None = None
    strategy: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(
            self.current_active_model_ref,
            field_name="current_active_model_ref",
        )
        if not isinstance(self.route_catalog, LlmModelRouteCatalog):
            raise TypeError("route_catalog must be LlmModelRouteCatalog")
        if self.retry_plan is not None and not isinstance(
            self.retry_plan,
            WorkItemRetryPlan,
        ):
            raise TypeError("retry_plan must be WorkItemRetryPlan when provided")
        if self.strategy is not None:
            _require_non_empty_text(self.strategy, field_name="strategy")


@dataclass(frozen=True, slots=True)
class ResolveLlmDispatchPreparationStrategyResult:
    active_model_ref: str
    strategy_applied: str | None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.active_model_ref, field_name="active_model_ref")
        if self.strategy_applied is not None:
            _require_non_empty_text(
                self.strategy_applied,
                field_name="strategy_applied",
            )


class ResolveLlmDispatchPreparationStrategy:
    def execute(
        self,
        command: ResolveLlmDispatchPreparationStrategyCommand,
    ) -> ResolveLlmDispatchPreparationStrategyResult:
        if command.retry_plan is not None:
            return _resolve_retry_plan(command)

        return _resolve_legacy_strategy(command)


def _resolve_retry_plan(
    command: ResolveLlmDispatchPreparationStrategyCommand,
) -> ResolveLlmDispatchPreparationStrategyResult:
    retry_plan = command.retry_plan
    if retry_plan is None:
        raise ValueError("retry_plan is required")

    if retry_plan in {
        WorkItemRetryPlan.RETRY_SAME_ROUTE,
        WorkItemRetryPlan.RETRY_ALTERNATE_ROUTE,
        WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW,
    }:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=command.current_active_model_ref,
            strategy_applied=retry_plan.value,
        )

    if retry_plan is WorkItemRetryPlan.RETRY_VALIDATION_CHECK_ROUTE:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=_validation_check_model_ref(
                command.route_catalog,
            ),
            strategy_applied=retry_plan.value,
        )

    if retry_plan is WorkItemRetryPlan.RETRY_DAILY_FALLBACK_ROUTE:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=_first_daily_limit_fallback(command.route_catalog),
            strategy_applied=retry_plan.value,
        )

    if retry_plan is WorkItemRetryPlan.RETRY_LARGER_OUTPUT_LIMIT_ROUTE:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=_first_larger_output_fallback(
                current_model_ref=command.current_active_model_ref,
                route_catalog=command.route_catalog,
            ),
            strategy_applied=retry_plan.value,
        )

    if retry_plan is WorkItemRetryPlan.RETRY_LARGER_INPUT_LIMIT_ROUTE:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=_first_larger_input_fallback(
                current_model_ref=command.current_active_model_ref,
                route_catalog=command.route_catalog,
            ),
            strategy_applied=retry_plan.value,
        )

    raise ValueError(f"retry_plan cannot be prepared for dispatch: {retry_plan}")


def _resolve_legacy_strategy(
    command: ResolveLlmDispatchPreparationStrategyCommand,
) -> ResolveLlmDispatchPreparationStrategyResult:
    strategy = command.strategy

    if strategy is None:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=command.current_active_model_ref,
            strategy_applied=None,
        )

    if strategy in {"SAME_MODEL", "RETRY_SAME_ROUTE"}:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=command.current_active_model_ref,
            strategy_applied=strategy,
        )

    legacy_claim_builder_validation_check_strategies = {
        "EMPTY_CLAIMS_CHECK" + "_MODEL_REQUIRED",
        "RETRY_EMPTY_CLAIMS_CHECK" + "_MODEL",
    }
    if strategy in legacy_claim_builder_validation_check_strategies:
        raise ValueError(
            "phase-specific validation check strategy must be converted to retry_plan"
        )

    if strategy == "RETRY_FALLBACK_MODEL":
        raise ValueError(
            "RETRY_FALLBACK_MODEL is not an explicit dispatch preparation "
            "strategy; use a specific retry cause strategy instead"
        )

    if strategy == "FALLBACK_MODEL_REQUIRED":
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=_first_automatic_fallback(command.route_catalog),
            strategy_applied=strategy,
        )

    if strategy in {
        "DAILY_LIMIT_FALLBACK_MODEL_REQUIRED",
        "RETRY_DAILY_LIMIT_FALLBACK_MODEL",
    }:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=_first_daily_limit_fallback(command.route_catalog),
            strategy_applied=strategy,
        )

    if strategy in {
        "LARGER_OUTPUT_LIMIT_MODEL_REQUIRED",
        "RETRY_LARGER_OUTPUT_LIMIT_MODEL",
    }:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=_first_larger_output_fallback(
                current_model_ref=command.current_active_model_ref,
                route_catalog=command.route_catalog,
            ),
            strategy_applied=strategy,
        )

    if strategy in {
        "LARGER_INPUT_LIMIT_MODEL_REQUIRED",
        "RETRY_LARGER_INPUT_LIMIT_MODEL",
    }:
        return ResolveLlmDispatchPreparationStrategyResult(
            active_model_ref=_first_larger_input_fallback(
                current_model_ref=command.current_active_model_ref,
                route_catalog=command.route_catalog,
            ),
            strategy_applied=strategy,
        )

    raise ValueError(f"unknown llm dispatch preparation strategy: {strategy}")


def _first_automatic_fallback(route_catalog: LlmModelRouteCatalog) -> str:
    fallback_model_refs = route_catalog.automatic_fallback_model_refs()
    if not fallback_model_refs:
        raise ValueError("route catalog has no automatic fallback model refs")
    return fallback_model_refs[0]


def _first_daily_limit_fallback(route_catalog: LlmModelRouteCatalog) -> str:
    fallback_model_refs = route_catalog.automatic_fallback_model_refs_for_daily_limit()
    if not fallback_model_refs:
        raise ValueError("route catalog has no daily-limit fallback model refs")
    return fallback_model_refs[0]


def _validation_check_model_ref(route_catalog: LlmModelRouteCatalog) -> str:
    gpt_oss_120b = route_catalog.route_for_model_ref("openai/gpt-oss-120b")
    if gpt_oss_120b is None:
        raise ValueError("route catalog is missing openai/gpt-oss-120b")
    return gpt_oss_120b.model_ref


def _first_larger_output_fallback(
    *,
    current_model_ref: str,
    route_catalog: LlmModelRouteCatalog,
) -> str:
    fallback_model_refs = (
        route_catalog.automatic_fallback_model_refs_with_larger_output_limit(
            current_model_ref,
        )
    )
    if not fallback_model_refs:
        raise ValueError(
            "route catalog has no automatic fallback model with larger output limit"
        )
    return fallback_model_refs[0]


def _first_larger_input_fallback(
    *,
    current_model_ref: str,
    route_catalog: LlmModelRouteCatalog,
) -> str:
    fallback_model_refs = (
        route_catalog.automatic_fallback_model_refs_with_larger_input_limit(
            current_model_ref,
        )
    )
    if not fallback_model_refs:
        raise ValueError(
            "route catalog has no automatic fallback model with larger input limit"
        )
    return fallback_model_refs[0]


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
