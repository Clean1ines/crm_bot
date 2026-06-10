from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
    WorkItemAttemptDispatchReadRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_outcome_repository_port import (
    WorkItemAttemptOutcomeStatus,
)
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcome,
    RecordWorkItemAttemptOutcomeCommand,
    RecordWorkItemAttemptOutcomeResult,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
    LlmDispatchExecutorPort,
)


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttemptCommand:
    attempt_id: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttemptResult:
    dispatch: WorkItemAttemptDispatchForExecution
    llm_result: LlmDispatchExecutionResult
    outcome_result: RecordWorkItemAttemptOutcomeResult


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttempt:
    dispatch_repository: WorkItemAttemptDispatchReadRepositoryPort
    llm_executor: LlmDispatchExecutorPort
    outcome_recorder: RecordWorkItemAttemptOutcome

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> ExecutePreparedLlmDispatchAttemptResult:
        dispatch = await self.dispatch_repository.get_dispatch_for_execution(
            attempt_id=command.attempt_id,
        )
        if dispatch is None:
            raise ValueError("dispatch attempt not found")

        llm_result = await self.llm_executor.execute_dispatch(
            LlmDispatchExecutionInput(
                attempt_id=dispatch.attempt_id,
                work_item_id=dispatch.work_item_id,
                attempt_number=dispatch.attempt_number,
                dispatch_payload=dispatch.dispatch_payload,
                started_at=dispatch.started_at,
            ),
        )

        outcome_result = await self.outcome_recorder.execute(
            RecordWorkItemAttemptOutcomeCommand(
                attempt_id=dispatch.attempt_id,
                work_item_id=dispatch.work_item_id,
                attempt_number=dispatch.attempt_number,
                lease_token=dispatch.lease_token,
                finished_at=llm_result.finished_at,
                outcome_status=_map_status(llm_result.status),
                error_kind=llm_result.error_kind,
                next_attempt_at=llm_result.next_attempt_at,
            ),
        )

        return ExecutePreparedLlmDispatchAttemptResult(
            dispatch=dispatch,
            llm_result=llm_result,
            outcome_result=outcome_result,
        )


def _map_status(
    status: LlmDispatchExecutionStatus,
) -> WorkItemAttemptOutcomeStatus:
    if status is LlmDispatchExecutionStatus.SUCCEEDED:
        return WorkItemAttemptOutcomeStatus.SUCCEEDED
    if status is LlmDispatchExecutionStatus.RETRYABLE_FAILED:
        return WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED
    if status is LlmDispatchExecutionStatus.TERMINAL_FAILED:
        return WorkItemAttemptOutcomeStatus.TERMINAL_FAILED
    if status is LlmDispatchExecutionStatus.DEFERRED:
        return WorkItemAttemptOutcomeStatus.DEFERRED
    raise ValueError("unsupported LLM dispatch execution status")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
