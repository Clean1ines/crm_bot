from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionStatus,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttempt,
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)
from src.interfaces.composition.persist_successful_llm_dispatch_artifacts import (
    PersistSuccessfulLlmDispatchArtifacts,
    PersistSuccessfulLlmDispatchArtifactsCommand,
    PersistSuccessfulLlmDispatchArtifactsResult,
)


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttemptWithArtifactsCommand:
    attempt_id: str
    artifact_created_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_timezone_aware(
            self.artifact_created_at,
            field_name="artifact_created_at",
        )


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttemptWithArtifactsResult:
    execution_result: ExecutePreparedLlmDispatchAttemptResult
    artifact_result: PersistSuccessfulLlmDispatchArtifactsResult | None


@dataclass(frozen=True, slots=True)
class ExecutePreparedLlmDispatchAttemptWithArtifacts:
    execute_attempt: ExecutePreparedLlmDispatchAttempt
    persist_success_artifacts: PersistSuccessfulLlmDispatchArtifacts

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptWithArtifactsCommand,
    ) -> ExecutePreparedLlmDispatchAttemptWithArtifactsResult:
        execution_result = await self.execute_attempt.execute(
            ExecutePreparedLlmDispatchAttemptCommand(
                attempt_id=command.attempt_id,
            ),
        )

        artifact_result: PersistSuccessfulLlmDispatchArtifactsResult | None = None
        if execution_result.llm_result.status is LlmDispatchExecutionStatus.SUCCEEDED:
            artifact_result = await self.persist_success_artifacts.execute(
                PersistSuccessfulLlmDispatchArtifactsCommand(
                    dispatch=execution_result.dispatch,
                    llm_result=execution_result.llm_result,
                    created_at=command.artifact_created_at,
                ),
            )

        return ExecutePreparedLlmDispatchAttemptWithArtifactsResult(
            execution_result=execution_result,
            artifact_result=artifact_result,
        )


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
