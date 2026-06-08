from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.state_machines.llm_task_state_machine import (
    InvalidLlmTaskTransition,
    LlmTaskStateMachine,
)
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import (
    OutputContractRef,
)
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.quota_decision import (
    QuotaDecision,
    QuotaDecisionKind,
)
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage
from src.contexts.llm_runtime.domain.value_objects.validation_result import (
    LlmValidationResult,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route() -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId("model-1"),
        account_ref=ProviderAccountRef("account-1"),
    )


def _task() -> LlmTask:
    return LlmTask(
        task_id="task-1",
        prompt_id="generic_prompt",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("input-1"),
        output_contract_ref=OutputContractRef("contract-1"),
    )


def _running_task() -> LlmTask:
    return LlmTaskStateMachine.start_ready(_task(), route=_route())


def test_llm_task_statuses_are_generic() -> None:
    assert {status.value for status in LlmTaskStatus} == {
        "ready",
        "running",
        "succeeded",
        "deferred",
        "retryable_failed",
        "terminal_failed",
        "cancelled",
    }


def test_start_ready_selects_route_and_increments_attempt_count() -> None:
    running = LlmTaskStateMachine.start_ready(_task(), route=_route())

    assert running.status is LlmTaskStatus.RUNNING
    assert running.selected_route == _route()
    assert running.attempt_count == 1


def test_success_requires_running_task() -> None:
    succeeded = LlmTaskStateMachine.succeed_running(_running_task())

    assert succeeded.status is LlmTaskStatus.SUCCEEDED
    assert succeeded.status.is_terminal

    with pytest.raises(InvalidLlmTaskTransition):
        LlmTaskStateMachine.succeed_running(_task())


def test_defer_running_task_requires_timezone_aware_wait_until() -> None:
    running = _running_task()
    wait_until = _now() + timedelta(seconds=60)

    deferred = LlmTaskStateMachine.defer_running(
        running,
        wait_until=wait_until,
        error_kind=LlmErrorKind.MINUTE_LIMIT,
    )

    assert deferred.status is LlmTaskStatus.DEFERRED
    assert deferred.wait_until == wait_until
    assert deferred.last_error_kind is LlmErrorKind.MINUTE_LIMIT

    with pytest.raises(ValueError):
        LlmTaskStateMachine.defer_running(
            running,
            wait_until=datetime(2026, 6, 8, 12, 0),
            error_kind=LlmErrorKind.MINUTE_LIMIT,
        )


def test_retryable_and_terminal_failures_are_explicit() -> None:
    running = _running_task()

    retryable = LlmTaskStateMachine.fail_running_retryable(
        running,
        error_kind=LlmErrorKind.NETWORK_ERROR,
    )

    assert retryable.status is LlmTaskStatus.RETRYABLE_FAILED
    assert retryable.last_error_kind is LlmErrorKind.NETWORK_ERROR

    terminal = LlmTaskStateMachine.fail_running_terminal(
        running,
        error_kind=LlmErrorKind.AUTH_ERROR,
    )

    assert terminal.status is LlmTaskStatus.TERMINAL_FAILED
    assert terminal.last_error_kind is LlmErrorKind.AUTH_ERROR


def test_cancel_non_terminal_task() -> None:
    cancelled = LlmTaskStateMachine.cancel(
        _running_task(),
        error_kind=LlmErrorKind.UNKNOWN,
    )

    assert cancelled.status is LlmTaskStatus.CANCELLED
    assert cancelled.status.is_terminal

    with pytest.raises(InvalidLlmTaskTransition):
        LlmTaskStateMachine.cancel(cancelled)


def test_quota_decision_wait_until_requires_timestamp() -> None:
    decision = QuotaDecision(
        kind=QuotaDecisionKind.WAIT_UNTIL,
        reason=LlmErrorKind.MINUTE_LIMIT,
        wait_until=_now() + timedelta(seconds=60),
    )

    assert decision.kind is QuotaDecisionKind.WAIT_UNTIL

    with pytest.raises(ValueError):
        QuotaDecision(kind=QuotaDecisionKind.WAIT_UNTIL)

    with pytest.raises(ValueError):
        QuotaDecision(
            kind=QuotaDecisionKind.ALLOW,
            wait_until=_now(),
        )


def test_token_usage_total_and_validation_result_invariants() -> None:
    usage = TokenUsage(input_tokens=10, output_tokens=5)
    assert usage.total_tokens == 15

    assert LlmValidationResult.valid().is_valid

    invalid = LlmValidationResult.invalid("missing_field")
    assert not invalid.is_valid
    assert invalid.error_codes == ("missing_field",)

    with pytest.raises(ValueError):
        LlmValidationResult(is_valid=True, error_codes=("unexpected",))

    with pytest.raises(ValueError):
        LlmValidationResult(is_valid=False)


def test_llm_attempt_requires_valid_timestamps() -> None:
    attempt = LlmAttempt(
        attempt_id="attempt-1",
        task_id="task-1",
        attempt_number=1,
        route=_route(),
        started_at=_now(),
        finished_at=_now() + timedelta(seconds=1),
        usage=TokenUsage(input_tokens=1, output_tokens=2),
    )

    assert attempt.usage is not None
    assert attempt.usage.total_tokens == 3

    with pytest.raises(ValueError):
        LlmAttempt(
            attempt_id="attempt-1",
            task_id="task-1",
            attempt_number=0,
            route=_route(),
            started_at=_now(),
        )
