from __future__ import annotations

from enum import StrEnum


class WorkItemRetryPlan(StrEnum):
    """Canonical Execution Runtime retry intent.

    Status answers only whether the work item is executable, leased, terminal, or
    retryable. RetryPlan answers *how* a retryable item should be retried.

    This vocabulary is intentionally generic and must not know business facts,
    bounded-context payloads, admission pools, or implementation details.
    """

    RETRY_SAME_ROUTE = "retry_same_route"
    RETRY_ALTERNATE_ROUTE = "retry_alternate_route"
    RETRY_VALIDATION_CHECK_ROUTE = "retry_validation_check_route"
    RETRY_LARGER_INPUT_LIMIT_ROUTE = "retry_larger_input_limit_route"
    RETRY_LARGER_OUTPUT_LIMIT_ROUTE = "retry_larger_output_limit_route"
    RETRY_DAILY_FALLBACK_ROUTE = "retry_daily_fallback_route"
    WAIT_NEAREST_ADMISSION_WINDOW = "wait_nearest_admission_window"
    SPLIT_WORK_PAYLOAD = "split_work_payload"
    WAIT_DAILY_ADMISSION_RESET = "wait_daily_admission_reset"
    TERMINAL = "terminal"
