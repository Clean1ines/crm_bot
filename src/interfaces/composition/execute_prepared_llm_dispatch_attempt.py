from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
    WorkItemAttemptDispatchReadRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_outcome_repository_port import (
    RecordedWorkItemAttemptOutcome,
    WorkItemAttemptOutcomeRepositoryPort,
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


LOGGER = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LlmDispatchOutputValidationResult:
    status: LlmDispatchExecutionStatus
    error_kind: str | None
    next_attempt_at: datetime | None
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.status, LlmDispatchExecutionStatus):
            raise TypeError("status must be LlmDispatchExecutionStatus")
        if self.error_kind is not None:
            _require_non_empty_text(self.error_kind, field_name="error_kind")
        if self.next_attempt_at is not None:
            _require_timezone_aware(self.next_attempt_at, field_name="next_attempt_at")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be Mapping")

        if self.status is LlmDispatchExecutionStatus.SUCCEEDED:
            if self.error_kind is not None:
                raise ValueError("error_kind must be None for succeeded validation")
            if self.next_attempt_at is not None:
                raise ValueError(
                    "next_attempt_at must be None for succeeded validation"
                )
            return

        if self.error_kind is None:
            raise ValueError("error_kind is required for non-succeeded validation")

        if self.status in {
            LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            LlmDispatchExecutionStatus.DEFERRED,
        }:
            if self.next_attempt_at is None:
                raise ValueError(
                    "next_attempt_at is required for retryable/deferred validation"
                )


class LlmDispatchOutputValidationPort(Protocol):
    def validate(
        self,
        *,
        dispatch_payload: Mapping[str, object],
        output_payload: Mapping[str, object] | None,
        llm_status: LlmDispatchExecutionStatus,
        finished_at: datetime,
        attempt_number: int,
    ) -> LlmDispatchOutputValidationResult: ...


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttemptCommand:
    attempt_id: str
    output_validator: LlmDispatchOutputValidationPort | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttemptResult:
    dispatch: WorkItemAttemptDispatchForExecution
    llm_result: LlmDispatchExecutionResult
    outcome_result: RecordWorkItemAttemptOutcomeResult
    validation_metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.validation_metadata is not None and not isinstance(
            self.validation_metadata,
            Mapping,
        ):
            raise TypeError("validation_metadata must be Mapping when provided")


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttempt:
    dispatch_repository: WorkItemAttemptDispatchReadRepositoryPort
    llm_executor: LlmDispatchExecutorPort
    outcome_recorder: RecordWorkItemAttemptOutcome
    recorded_outcome_reader: WorkItemAttemptOutcomeRepositoryPort | None = None

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> ExecutePreparedLlmDispatchAttemptResult:
        dispatch = await self.dispatch_repository.get_dispatch_for_execution(
            attempt_id=command.attempt_id,
        )
        if dispatch is None:
            LOGGER.warning(
                "knowledge_llm_execute_dispatch_missing",
                attempt_id=command.attempt_id,
            )
            raise ValueError("dispatch attempt not found")

        LOGGER.info(
            "knowledge_llm_execute_dispatch_loaded",
            attempt_id=dispatch.attempt_id,
            work_item_id=dispatch.work_item_id,
            attempt_number=dispatch.attempt_number,
            started_at=dispatch.started_at.isoformat(),
            dispatch_payload_keys=sorted(dispatch.dispatch_payload.keys()),
            has_output_validator=command.output_validator is not None,
        )

        if self.recorded_outcome_reader is not None:
            recorded_outcome = (
                await self.recorded_outcome_reader.get_recorded_attempt_outcome(
                    attempt_id=dispatch.attempt_id,
                )
            )
            if recorded_outcome is not None:
                return ExecutePreparedLlmDispatchAttemptResult(
                    dispatch=dispatch,
                    llm_result=_llm_result_from_recorded_outcome(
                        recorded_outcome,
                    ),
                    outcome_result=RecordWorkItemAttemptOutcomeResult(
                        work_item=recorded_outcome.work_item,
                    ),
                    validation_metadata=None,
                )

        provider_llm_result = await self.llm_executor.execute_dispatch(
            LlmDispatchExecutionInput(
                attempt_id=dispatch.attempt_id,
                work_item_id=dispatch.work_item_id,
                attempt_number=dispatch.attempt_number,
                dispatch_payload=dispatch.dispatch_payload,
                started_at=dispatch.started_at,
            ),
        )
        LOGGER.info(
            "knowledge_llm_execute_provider_result",
            attempt_id=dispatch.attempt_id,
            work_item_id=dispatch.work_item_id,
            attempt_number=dispatch.attempt_number,
            provider_status=provider_llm_result.status.value,
            provider_error_kind=provider_llm_result.error_kind,
            provider_next_attempt_at=provider_llm_result.next_attempt_at.isoformat()
            if provider_llm_result.next_attempt_at is not None
            else None,
            has_output_payload=provider_llm_result.output_payload is not None,
            has_capacity_observation=provider_llm_result.capacity_observation
            is not None,
        )

        validation_result = _validate_output_if_requested(
            output_validator=command.output_validator,
            dispatch=dispatch,
            provider_llm_result=provider_llm_result,
        )
        llm_result = _effective_llm_result(
            provider_llm_result=provider_llm_result,
            validation_result=validation_result,
        )
        LOGGER.info(
            "knowledge_llm_execute_effective_result",
            attempt_id=dispatch.attempt_id,
            work_item_id=dispatch.work_item_id,
            attempt_number=dispatch.attempt_number,
            effective_status=llm_result.status.value,
            effective_error_kind=llm_result.error_kind,
            effective_next_attempt_at=llm_result.next_attempt_at.isoformat()
            if llm_result.next_attempt_at is not None
            else None,
            validation_status=validation_result.status.value
            if validation_result is not None
            else None,
            validation_error_kind=validation_result.error_kind
            if validation_result is not None
            else None,
            validation_metadata=dict(validation_result.metadata)
            if validation_result is not None
            else None,
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
        LOGGER.info(
            "knowledge_llm_execute_outcome_recorded",
            attempt_id=dispatch.attempt_id,
            work_item_id=dispatch.work_item_id,
            attempt_number=dispatch.attempt_number,
            effective_status=llm_result.status.value,
            effective_error_kind=llm_result.error_kind,
        )

        return ExecutePreparedLlmDispatchAttemptResult(
            dispatch=dispatch,
            llm_result=llm_result,
            outcome_result=outcome_result,
            validation_metadata=(
                dict(validation_result.metadata)
                if validation_result is not None
                else None
            ),
        )


def _llm_result_from_recorded_outcome(
    recorded_outcome: RecordedWorkItemAttemptOutcome,
) -> LlmDispatchExecutionResult:
    status = _map_recorded_outcome_status(recorded_outcome.outcome_status)
    return LlmDispatchExecutionResult(
        status=status,
        finished_at=recorded_outcome.finished_at,
        output_payload={"already_recorded": True}
        if status is LlmDispatchExecutionStatus.SUCCEEDED
        else None,
        error_kind=recorded_outcome.error_kind,
        next_attempt_at=recorded_outcome.next_attempt_at,
    )


def _map_recorded_outcome_status(
    status: WorkItemAttemptOutcomeStatus,
) -> LlmDispatchExecutionStatus:
    if status is WorkItemAttemptOutcomeStatus.SUCCEEDED:
        return LlmDispatchExecutionStatus.SUCCEEDED
    if status is WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED:
        return LlmDispatchExecutionStatus.RETRYABLE_FAILED
    if status is WorkItemAttemptOutcomeStatus.TERMINAL_FAILED:
        return LlmDispatchExecutionStatus.TERMINAL_FAILED
    if status is WorkItemAttemptOutcomeStatus.DEFERRED:
        return LlmDispatchExecutionStatus.DEFERRED
    raise ValueError("unsupported recorded attempt outcome status")


def _validate_output_if_requested(
    *,
    output_validator: LlmDispatchOutputValidationPort | None,
    dispatch: WorkItemAttemptDispatchForExecution,
    provider_llm_result: LlmDispatchExecutionResult,
) -> LlmDispatchOutputValidationResult | None:
    if output_validator is None:
        return None
    if provider_llm_result.status is not LlmDispatchExecutionStatus.SUCCEEDED:
        return None

    return output_validator.validate(
        dispatch_payload=dispatch.dispatch_payload,
        output_payload=provider_llm_result.output_payload,
        llm_status=provider_llm_result.status,
        finished_at=provider_llm_result.finished_at,
        attempt_number=dispatch.attempt_number,
    )


def _effective_llm_result(
    *,
    provider_llm_result: LlmDispatchExecutionResult,
    validation_result: LlmDispatchOutputValidationResult | None,
) -> LlmDispatchExecutionResult:
    if validation_result is None:
        return provider_llm_result

    return LlmDispatchExecutionResult(
        status=validation_result.status,
        finished_at=provider_llm_result.finished_at,
        output_payload=provider_llm_result.output_payload,
        error_kind=validation_result.error_kind,
        next_attempt_at=validation_result.next_attempt_at,
        capacity_observation=provider_llm_result.capacity_observation,
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


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
