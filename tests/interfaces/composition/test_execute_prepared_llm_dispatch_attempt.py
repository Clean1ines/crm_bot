from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_outcome_repository_port import (
    WorkItemAttemptOutcomeRecord,
    WorkItemAttemptOutcomeStatus,
)
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcome,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttempt,
    ExecutePreparedLlmDispatchAttemptCommand,
)


class FakeDispatchRepository:
    def __init__(self, dispatch: WorkItemAttemptDispatchForExecution | None) -> None:
        self.dispatch = dispatch
        self.attempt_ids: list[str] = []

    async def get_dispatch_for_execution(
        self,
        *,
        attempt_id: str,
    ) -> WorkItemAttemptDispatchForExecution | None:
        self.attempt_ids.append(attempt_id)
        return self.dispatch


class FakeLlmExecutor:
    def __init__(self, result: LlmDispatchExecutionResult) -> None:
        self.result = result
        self.inputs: list[LlmDispatchExecutionInput] = []

    async def execute_dispatch(
        self,
        execution_input: LlmDispatchExecutionInput,
    ) -> LlmDispatchExecutionResult:
        self.inputs.append(execution_input)
        return self.result


class FakeOutcomeRepository:
    def __init__(self) -> None:
        self.records: list[WorkItemAttemptOutcomeRecord] = []

    async def record_attempt_outcome(
        self,
        record: WorkItemAttemptOutcomeRecord,
    ) -> WorkItem:
        self.records.append(record)
        return WorkItem(
            work_item_id=record.work_item_id,
            work_kind=WorkKind("execution.test"),
            status=WorkItemStatus.COMPLETED,
        )


def _started_at() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 6, 11, 12, 1, tzinfo=UTC)


def _next_attempt_at() -> datetime:
    return _finished_at() + timedelta(minutes=5)


def _dispatch_payload() -> dict[str, object]:
    return {
        "work_item_id": "work-1",
        "schedule_payload": {"provider_messages": []},
        "llm_allocation": {"slot_index": 0},
        "llm_execution_settings": {"reasoning_enabled": False},
    }


def _dispatch() -> WorkItemAttemptDispatchForExecution:
    return WorkItemAttemptDispatchForExecution(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        lease_token=LeaseToken("lease-token-1"),
        worker_ref="worker-1",
        dispatch_payload=_dispatch_payload(),
        started_at=_started_at(),
    )


def _runner(
    *,
    dispatch: WorkItemAttemptDispatchForExecution | None,
    llm_result: LlmDispatchExecutionResult,
    outcome_repository: FakeOutcomeRepository,
) -> ExecutePreparedLlmDispatchAttempt:
    return ExecutePreparedLlmDispatchAttempt(
        dispatch_repository=FakeDispatchRepository(dispatch=dispatch),
        llm_executor=FakeLlmExecutor(result=llm_result),
        outcome_recorder=RecordWorkItemAttemptOutcome(
            repository=outcome_repository,
        ),
    )


async def _execute(
    *,
    dispatch: WorkItemAttemptDispatchForExecution | None = None,
    llm_result: LlmDispatchExecutionResult,
    outcome_repository: FakeOutcomeRepository | None = None,
):
    repository = outcome_repository or FakeOutcomeRepository()
    runner = _runner(
        dispatch=dispatch if dispatch is not None else _dispatch(),
        llm_result=llm_result,
        outcome_repository=repository,
    )
    result = await runner.execute(
        ExecutePreparedLlmDispatchAttemptCommand(attempt_id="attempt-1"),
    )
    return result, runner, repository


@pytest.mark.asyncio
async def test_success_result_maps_to_successful_outcome() -> None:
    result, _, repository = await _execute(
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_finished_at(),
            output_payload={"raw_text": "{}"},
        ),
    )

    assert result.outcome_result.work_item.status is WorkItemStatus.COMPLETED
    assert (
        repository.records[0].outcome_status is WorkItemAttemptOutcomeStatus.SUCCEEDED
    )
    assert repository.records[0].error_kind is None


@pytest.mark.asyncio
async def test_retryable_failed_maps_to_retryable_outcome() -> None:
    _, _, repository = await _execute(
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            finished_at=_finished_at(),
            error_kind="request_too_large",
            next_attempt_at=_next_attempt_at(),
        ),
    )

    assert (
        repository.records[0].outcome_status
        is WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED
    )
    assert repository.records[0].error_kind == "request_too_large"
    assert repository.records[0].next_attempt_at == _next_attempt_at()


@pytest.mark.asyncio
async def test_terminal_failed_maps_to_terminal_outcome() -> None:
    _, _, repository = await _execute(
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
            finished_at=_finished_at(),
            error_kind="auth_error",
        ),
    )

    assert (
        repository.records[0].outcome_status
        is WorkItemAttemptOutcomeStatus.TERMINAL_FAILED
    )
    assert repository.records[0].error_kind == "auth_error"


@pytest.mark.asyncio
async def test_deferred_maps_to_deferred_outcome_with_next_attempt_at() -> None:
    _, _, repository = await _execute(
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.DEFERRED,
            finished_at=_finished_at(),
            error_kind="minute_limit",
            next_attempt_at=_next_attempt_at(),
        ),
    )

    assert repository.records[0].outcome_status is WorkItemAttemptOutcomeStatus.DEFERRED
    assert repository.records[0].error_kind == "minute_limit"
    assert repository.records[0].next_attempt_at == _next_attempt_at()


@pytest.mark.asyncio
async def test_dispatch_not_found_raises() -> None:
    outcome_repository = FakeOutcomeRepository()
    runner = _runner(
        dispatch=None,
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_finished_at(),
            output_payload={"raw_text": "{}"},
        ),
        outcome_repository=outcome_repository,
    )

    with pytest.raises(ValueError, match="dispatch attempt not found"):
        await runner.execute(
            ExecutePreparedLlmDispatchAttemptCommand(attempt_id="missing-attempt"),
        )

    assert outcome_repository.records == []


@pytest.mark.asyncio
async def test_llm_executor_receives_exact_dispatch_payload_and_started_at() -> None:
    dispatch = _dispatch()
    llm_result = LlmDispatchExecutionResult(
        status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_finished_at(),
        output_payload={"raw_text": "{}"},
    )
    outcome_repository = FakeOutcomeRepository()
    llm_executor = FakeLlmExecutor(result=llm_result)
    runner = ExecutePreparedLlmDispatchAttempt(
        dispatch_repository=FakeDispatchRepository(dispatch=dispatch),
        llm_executor=llm_executor,
        outcome_recorder=RecordWorkItemAttemptOutcome(
            repository=outcome_repository,
        ),
    )

    await runner.execute(
        ExecutePreparedLlmDispatchAttemptCommand(attempt_id="attempt-1")
    )

    assert llm_executor.inputs == [
        LlmDispatchExecutionInput(
            attempt_id="attempt-1",
            work_item_id="work-1",
            attempt_number=1,
            dispatch_payload=dispatch.dispatch_payload,
            started_at=dispatch.started_at,
        ),
    ]


def test_composition_does_not_import_legacy_provider_or_groq_paths() -> None:
    from pathlib import Path

    source = Path(
        "src/interfaces/composition/execute_prepared_llm_dispatch_attempt.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "GroqDispatchExecutor",
        "GroqProviderAdapter",
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
    )
    for marker in forbidden:
        assert marker not in source


@pytest.mark.asyncio
async def test_execution_result_exposes_capacity_observation_contract() -> None:
    capacity_observation = {
        "provider": "groq",
        "account_ref": "groq_org_primary",
        "model_ref": "qwen/qwen3-32b",
        "remaining_minute_requests": 1,
        "remaining_minute_tokens": 1000,
        "remaining_daily_requests": 10,
        "remaining_daily_tokens": 10000,
        "minute_reset_at": _finished_at() + timedelta(seconds=60),
        "daily_reset_at": None,
        "actual_prompt_tokens": 2,
        "actual_completion_tokens": 3,
        "actual_total_tokens": 5,
        "outcome_class": "succeeded",
        "observed_at": _finished_at(),
    }
    result, _, _ = await _execute(
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_finished_at(),
            output_payload={"raw_text": "{}"},
            capacity_observation=capacity_observation,
        ),
    )

    assert result.llm_result.capacity_observation == capacity_observation
