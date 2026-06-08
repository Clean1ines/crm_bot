from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.llm_runtime.application.policies.llm_execution_recording_policy import (
    LlmAttemptRecordingInput,
    LlmExecutionRecordingPolicy,
)
from src.contexts.llm_runtime.application.results.execute_llm_task_result import (
    ExecuteLlmTaskOutcome,
    ExecuteLlmTaskOutcomeKind,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import (
    LlmDailyLimitExhausted,
    LlmMinuteLimitHit,
    LlmTaskFailed,
    LlmTaskSucceeded,
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
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route() -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId("model-1"),
        account_ref=ProviderAccountRef("account-1"),
    )


def _task(
    status: LlmTaskStatus = LlmTaskStatus.SUCCEEDED,
    *,
    wait_until: datetime | None = None,
) -> LlmTask:
    return LlmTask(
        task_id="task-1",
        prompt_id="generic_prompt",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("input-1"),
        output_contract_ref=OutputContractRef("contract-1"),
        status=status,
        wait_until=wait_until,
    )


def _attempt_input() -> LlmAttemptRecordingInput:
    return LlmAttemptRecordingInput(
        attempt_id="attempt-1",
        attempt_number=1,
        route=_route(),
        started_at=_now(),
        finished_at=_now() + timedelta(seconds=1),
    )


def test_success_outcome_records_attempt_and_success_event() -> None:
    outcome = ExecuteLlmTaskOutcome(
        kind=ExecuteLlmTaskOutcomeKind.SUCCEEDED,
        task=_task(),
        raw_text='{"ok": true}',
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )

    command = LlmExecutionRecordingPolicy().build_record_command(
        outcome=outcome,
        attempt_input=_attempt_input(),
        occurred_at=_now(),
    )

    assert command.task == outcome.task
    assert command.attempt is not None
    assert command.attempt.usage == TokenUsage(input_tokens=10, output_tokens=5)
    assert command.attempt.error_kind is None
    assert len(command.events) == 1
    assert isinstance(command.events[0], LlmTaskSucceeded)


def test_deferred_minute_limit_records_minute_limit_event() -> None:
    wait_until = _now() + timedelta(seconds=60)
    outcome = ExecuteLlmTaskOutcome(
        kind=ExecuteLlmTaskOutcomeKind.DEFERRED,
        task=_task(status=LlmTaskStatus.DEFERRED, wait_until=wait_until),
        wait_until=wait_until,
        error_kind=LlmErrorKind.MINUTE_LIMIT,
    )

    command = LlmExecutionRecordingPolicy().build_record_command(
        outcome=outcome,
        attempt_input=_attempt_input(),
        occurred_at=_now(),
    )

    assert command.attempt is not None
    assert command.attempt.error_kind is LlmErrorKind.MINUTE_LIMIT
    assert len(command.events) == 1
    event = command.events[0]
    assert isinstance(event, LlmMinuteLimitHit)
    assert event.wait_until == wait_until


def test_daily_exhausted_outcome_records_daily_limit_event() -> None:
    outcome = ExecuteLlmTaskOutcome(
        kind=ExecuteLlmTaskOutcomeKind.DAILY_EXHAUSTED,
        task=_task(status=LlmTaskStatus.RETRYABLE_FAILED),
        error_kind=LlmErrorKind.DAILY_LIMIT,
    )

    command = LlmExecutionRecordingPolicy().build_record_command(
        outcome=outcome,
        attempt_input=_attempt_input(),
        occurred_at=_now(),
    )

    assert command.attempt is not None
    assert command.attempt.error_kind is LlmErrorKind.DAILY_LIMIT
    assert len(command.events) == 1
    assert isinstance(command.events[0], LlmDailyLimitExhausted)


def test_terminal_failed_outcome_records_failed_event() -> None:
    outcome = ExecuteLlmTaskOutcome(
        kind=ExecuteLlmTaskOutcomeKind.TERMINAL_FAILED,
        task=_task(status=LlmTaskStatus.TERMINAL_FAILED),
        error_kind=LlmErrorKind.AUTH_ERROR,
    )

    command = LlmExecutionRecordingPolicy().build_record_command(
        outcome=outcome,
        attempt_input=_attempt_input(),
        occurred_at=_now(),
    )

    assert command.attempt is not None
    assert command.attempt.error_kind is LlmErrorKind.AUTH_ERROR
    assert len(command.events) == 1
    event = command.events[0]
    assert isinstance(event, LlmTaskFailed)
    assert event.error_kind is LlmErrorKind.AUTH_ERROR


def test_route_change_required_records_failed_event_with_route_error() -> None:
    outcome = ExecuteLlmTaskOutcome(
        kind=ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED,
        task=_task(status=LlmTaskStatus.RETRYABLE_FAILED),
        route=_route(),
        error_kind=LlmErrorKind.REQUEST_TOO_LARGE,
    )

    command = LlmExecutionRecordingPolicy().build_record_command(
        outcome=outcome,
        attempt_input=_attempt_input(),
        occurred_at=_now(),
    )

    assert command.attempt is not None
    assert command.attempt.error_kind is LlmErrorKind.REQUEST_TOO_LARGE
    assert len(command.events) == 1
    assert isinstance(command.events[0], LlmTaskFailed)


def test_attempt_recording_input_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValueError):
        LlmAttemptRecordingInput(
            attempt_id="attempt-1",
            attempt_number=1,
            route=_route(),
            started_at=datetime(2026, 6, 8, 12, 0),
            finished_at=_now(),
        )

    with pytest.raises(ValueError):
        LlmAttemptRecordingInput(
            attempt_id="attempt-1",
            attempt_number=1,
            route=_route(),
            started_at=_now(),
            finished_at=_now() - timedelta(seconds=1),
        )
