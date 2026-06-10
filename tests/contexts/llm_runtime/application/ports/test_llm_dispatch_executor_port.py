from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
    LlmDispatchExecutorPort,
)


class FakeLlmDispatchExecutor(LlmDispatchExecutorPort):
    def __init__(self, result: LlmDispatchExecutionResult) -> None:
        self.result = result
        self.inputs: list[LlmDispatchExecutionInput] = []

    async def execute_dispatch(
        self,
        execution_input: LlmDispatchExecutionInput,
    ) -> LlmDispatchExecutionResult:
        self.inputs.append(execution_input)
        return self.result


def _started_at() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 6, 11, 12, 1, tzinfo=UTC)


def _next_attempt_at() -> datetime:
    return _finished_at() + timedelta(minutes=5)


def _dispatch_payload() -> dict[str, object]:
    return {
        "work_item_id": "work-1",
        "schedule_payload": {"source_unit_ref": "unit-1"},
        "llm_allocation": {"slot_index": 0},
        "llm_execution_settings": {"reasoning_enabled": False},
    }


def _execution_input(
    *,
    dispatch_payload: dict[str, object] | None = None,
    started_at: datetime | None = None,
) -> LlmDispatchExecutionInput:
    return LlmDispatchExecutionInput(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        dispatch_payload=dispatch_payload or _dispatch_payload(),
        started_at=started_at or _started_at(),
    )


def test_valid_input_accepts_dispatch_payload_with_required_keys() -> None:
    execution_input = _execution_input()

    assert execution_input.dispatch_payload["llm_execution_settings"] == {
        "reasoning_enabled": False,
    }


def test_input_rejects_missing_llm_execution_settings() -> None:
    payload = _dispatch_payload()
    payload.pop("llm_execution_settings")

    with pytest.raises(ValueError, match="llm_execution_settings"):
        _execution_input(dispatch_payload=payload)


def test_input_rejects_naive_started_at() -> None:
    with pytest.raises(ValueError, match="started_at"):
        _execution_input(started_at=datetime(2026, 6, 11, 12, 0))


def test_success_result_requires_output_payload() -> None:
    with pytest.raises(ValueError, match="output_payload"):
        LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_finished_at(),
        )


def test_success_result_rejects_error_kind() -> None:
    with pytest.raises(ValueError, match="error_kind"):
        LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_finished_at(),
            output_payload={"raw_text": "{}"},
            error_kind="unexpected",
        )


def test_retryable_failure_requires_error_kind() -> None:
    with pytest.raises(ValueError, match="error_kind"):
        LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            finished_at=_finished_at(),
        )


def test_terminal_failure_requires_error_kind() -> None:
    with pytest.raises(ValueError, match="error_kind"):
        LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
            finished_at=_finished_at(),
        )


def test_deferred_requires_error_kind() -> None:
    with pytest.raises(ValueError, match="error_kind"):
        LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.DEFERRED,
            finished_at=_finished_at(),
            next_attempt_at=_next_attempt_at(),
        )


def test_deferred_requires_future_next_attempt_at() -> None:
    with pytest.raises(ValueError, match="next_attempt_at"):
        LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.DEFERRED,
            finished_at=_finished_at(),
            error_kind="rate_limited",
        )

    with pytest.raises(ValueError, match="next_attempt_at"):
        LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.DEFERRED,
            finished_at=_finished_at(),
            error_kind="rate_limited",
            next_attempt_at=_finished_at(),
        )


@pytest.mark.asyncio
async def test_fake_executor_implementing_protocol_returns_result() -> None:
    execution_input = _execution_input()
    expected_result = LlmDispatchExecutionResult(
        status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_finished_at(),
        output_payload={"raw_text": "{}"},
    )
    executor = FakeLlmDispatchExecutor(result=expected_result)

    result = await executor.execute_dispatch(execution_input)

    assert result == expected_result
    assert executor.inputs == [execution_input]
