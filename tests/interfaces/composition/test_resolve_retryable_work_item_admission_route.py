from __future__ import annotations

from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.interfaces.composition.resolve_retryable_work_item_admission_route import (
    ResolveRetryableWorkItemAdmissionRoute,
    ResolveRetryableWorkItemAdmissionRouteCommand,
)


def _resolve(retry_plan: WorkItemRetryPlan):
    return ResolveRetryableWorkItemAdmissionRoute().execute(
        ResolveRetryableWorkItemAdmissionRouteCommand(
            current_model_ref="qwen/qwen3-32b",
            retry_plan=retry_plan,
            route_catalog=default_groq_llm_model_route_catalog(),
        )
    )


def test_same_route_retry_keeps_current_admission_lane() -> None:
    result = _resolve(WorkItemRetryPlan.RETRY_SAME_ROUTE)

    assert result.model_ref is None
    assert result.reason == "keep_current_admission_route"


def test_minute_wait_keeps_current_admission_lane() -> None:
    result = _resolve(WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW)

    assert result.model_ref is None
    assert result.reason == "keep_current_admission_route"


def test_validation_check_route_moves_to_gpt_oss_lane() -> None:
    result = _resolve(WorkItemRetryPlan.RETRY_VALIDATION_CHECK_ROUTE)

    assert result.model_ref == "openai/gpt-oss-120b"
    assert result.reason == "retry_validation_check_route"


def test_larger_output_route_moves_to_first_larger_output_fallback_lane() -> None:
    result = _resolve(WorkItemRetryPlan.RETRY_LARGER_OUTPUT_LIMIT_ROUTE)

    assert result.model_ref == "llama-3.3-70b-versatile"
    assert result.reason == "retry_larger_output_limit_route"


def test_larger_input_route_moves_to_first_larger_input_fallback_lane() -> None:
    result = _resolve(WorkItemRetryPlan.RETRY_LARGER_INPUT_LIMIT_ROUTE)

    assert result.model_ref == "llama-3.3-70b-versatile"
    assert result.reason == "retry_larger_input_limit_route"


def test_daily_fallback_route_moves_to_daily_safe_fallback_lane() -> None:
    result = _resolve(WorkItemRetryPlan.RETRY_DAILY_FALLBACK_ROUTE)

    assert result.model_ref == "llama-3.3-70b-versatile"
    assert result.reason == "retry_daily_fallback_route"


def test_split_payload_has_no_dispatch_route() -> None:
    result = _resolve(WorkItemRetryPlan.SPLIT_WORK_PAYLOAD)

    assert result.model_ref is None
    assert result.reason == "retry_plan_has_no_dispatch_route"
