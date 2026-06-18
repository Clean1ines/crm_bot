from __future__ import annotations

from enum import StrEnum


class WorkItemRetryPlan(StrEnum):
    """Canonical Execution Runtime retry intent.

    Status answers only whether the work item is executable, leased, terminal, or
    retryable. RetryPlan answers *how* a retryable item should be retried.

    This vocabulary is intentionally generic and must not know Workbench facts,
    prompts, source units, or provider-specific implementation details.
    """

    RETRY_SAME_MODEL = "retry_same_model"
    RETRY_OTHER_ORG = "retry_other_org"
    RETRY_SPECIAL_EMPTY_CLAIMS_CHECK_MODEL = "retry_special_empty_claims_check_model"
    RETRY_LARGER_CONTEXT_MODEL = "retry_larger_context_model"
    RETRY_LARGER_OUTPUT_MODEL = "retry_larger_output_model"
    RETRY_DAILY_FALLBACK_MODEL = "retry_daily_fallback_model"
    WAIT_NEAREST_CAPACITY_WINDOW = "wait_nearest_capacity_window"
    SPLIT_SOURCE_UNIT = "split_source_unit"
    WAIT_DAILY_CAPACITY_RESET = "wait_daily_capacity_reset"
    TERMINAL = "terminal"
