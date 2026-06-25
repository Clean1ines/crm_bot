from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.llm_runtime.application.capacity.resolve_llm_dispatch_preparation_strategy import (
    ResolveLlmDispatchPreparationStrategy,
    ResolveLlmDispatchPreparationStrategyCommand,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)


_RETRY_PLANS_THAT_KEEP_CURRENT_ROUTE = frozenset(
    {
        WorkItemRetryPlan.RETRY_SAME_ROUTE,
        WorkItemRetryPlan.RETRY_ALTERNATE_ROUTE,
        WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW,
    }
)

_RETRY_PLANS_WITHOUT_DISPATCH_ROUTE = frozenset(
    {
        WorkItemRetryPlan.SPLIT_WORK_PAYLOAD,
        WorkItemRetryPlan.WAIT_DAILY_ADMISSION_RESET,
        WorkItemRetryPlan.TERMINAL,
    }
)


@dataclass(frozen=True, slots=True)
class ResolveRetryableWorkItemAdmissionRouteCommand:
    current_model_ref: str
    retry_plan: WorkItemRetryPlan
    route_catalog: LlmModelRouteCatalog

    def __post_init__(self) -> None:
        _require_non_empty_text(self.current_model_ref, "current_model_ref")
        if not isinstance(self.retry_plan, WorkItemRetryPlan):
            raise TypeError("retry_plan must be WorkItemRetryPlan")
        if not isinstance(self.route_catalog, LlmModelRouteCatalog):
            raise TypeError("route_catalog must be LlmModelRouteCatalog")


@dataclass(frozen=True, slots=True)
class ResolveRetryableWorkItemAdmissionRouteResult:
    model_ref: str | None
    reason: str

    def __post_init__(self) -> None:
        if self.model_ref is not None:
            _require_non_empty_text(self.model_ref, "model_ref")
        _require_non_empty_text(self.reason, "reason")


class ResolveRetryableWorkItemAdmissionRoute:
    """Root policy for mapping retryable execution intent to admission route.

    It does not mutate projections, reserve provider capacity, lease work items,
    or know Workbench facts. It only answers whether a retryable work item should
    remain in its current shared admission lane or become eligible for another
    model lane.
    """

    def execute(
        self,
        command: ResolveRetryableWorkItemAdmissionRouteCommand,
    ) -> ResolveRetryableWorkItemAdmissionRouteResult:
        retry_plan = command.retry_plan

        if retry_plan in _RETRY_PLANS_THAT_KEEP_CURRENT_ROUTE:
            return ResolveRetryableWorkItemAdmissionRouteResult(
                model_ref=None,
                reason="keep_current_admission_route",
            )

        if retry_plan in _RETRY_PLANS_WITHOUT_DISPATCH_ROUTE:
            return ResolveRetryableWorkItemAdmissionRouteResult(
                model_ref=None,
                reason="retry_plan_has_no_dispatch_route",
            )

        resolved = ResolveLlmDispatchPreparationStrategy().execute(
            ResolveLlmDispatchPreparationStrategyCommand(
                current_active_model_ref=command.current_model_ref,
                route_catalog=command.route_catalog,
                retry_plan=retry_plan,
            )
        )
        if resolved.active_model_ref == command.current_model_ref:
            return ResolveRetryableWorkItemAdmissionRouteResult(
                model_ref=None,
                reason="resolved_route_matches_current_route",
            )

        return ResolveRetryableWorkItemAdmissionRouteResult(
            model_ref=resolved.active_model_ref,
            reason=retry_plan.value,
        )


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
