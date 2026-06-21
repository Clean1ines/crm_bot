from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.contexts.execution_runtime.application.ports.work_item_attempt_outcome_repository_port import (
    WorkItemAttemptOutcomeRecord,
    WorkItemAttemptOutcomeStatus,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionStatus,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    LlmDispatchOutputValidationResult,
)


def _now() -> datetime:
    return datetime(2026, 6, 19, 13, 0, tzinfo=UTC)


def test_validation_retryable_failed_can_be_immediate_without_next_attempt_at() -> None:
    result = LlmDispatchOutputValidationResult(
        status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
        error_kind="claim_builder_output_validation_failed",
        next_attempt_at=None,
        metadata={"retry_recommended": True},
    )

    assert result.next_attempt_at is None


def test_validation_deferred_still_requires_next_attempt_at() -> None:
    with pytest.raises(ValueError, match="deferred validation"):
        LlmDispatchOutputValidationResult(
            status=LlmDispatchExecutionStatus.DEFERRED,
            error_kind="minute_limit",
            next_attempt_at=None,
            metadata={},
        )


def test_retryable_outcome_record_can_be_immediate_without_next_attempt_at() -> None:
    record = WorkItemAttemptOutcomeRecord(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        lease_token=LeaseToken("lease-token-1"),
        finished_at=_now(),
        outcome_status=WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED,
        error_kind="claim_builder_output_validation_failed",
        next_attempt_at=None,
        retry_plan=WorkItemRetryPlan.RETRY_SAME_ROUTE,
    )

    assert record.next_attempt_at is None


def test_deferred_outcome_record_still_requires_next_attempt_at() -> None:
    with pytest.raises(ValueError, match="deferred outcomes"):
        WorkItemAttemptOutcomeRecord(
            attempt_id="attempt-1",
            work_item_id="work-1",
            attempt_number=1,
            lease_token=LeaseToken("lease-token-1"),
            finished_at=_now(),
            outcome_status=WorkItemAttemptOutcomeStatus.DEFERRED,
            error_kind="minute_limit",
            next_attempt_at=None,
            retry_plan=WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW,
        )


def test_deferred_outcome_record_accepts_future_next_attempt_at() -> None:
    record = WorkItemAttemptOutcomeRecord(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        lease_token=LeaseToken("lease-token-1"),
        finished_at=_now(),
        outcome_status=WorkItemAttemptOutcomeStatus.DEFERRED,
        error_kind="minute_limit",
        next_attempt_at=_now() + timedelta(seconds=60),
        retry_plan=WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW,
    )

    assert record.next_attempt_at == _now() + timedelta(seconds=60)
