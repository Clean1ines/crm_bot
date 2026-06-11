from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
)
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcomeResult,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttempt,
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt_with_artifacts import (
    ExecutePreparedLlmDispatchAttemptWithArtifacts,
    ExecutePreparedLlmDispatchAttemptWithArtifactsCommand,
)
from src.interfaces.composition.persist_successful_llm_dispatch_artifacts import (
    PersistSuccessfulLlmDispatchArtifacts,
    PersistSuccessfulLlmDispatchArtifactsCommand,
    PersistSuccessfulLlmDispatchArtifactsResult,
)


class FakeExecutePreparedLlmDispatchAttempt:
    def __init__(self, result: ExecutePreparedLlmDispatchAttemptResult) -> None:
        self.result = result
        self.commands: list[ExecutePreparedLlmDispatchAttemptCommand] = []

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> ExecutePreparedLlmDispatchAttemptResult:
        self.commands.append(command)
        return self.result


class FakePersistSuccessfulLlmDispatchArtifacts:
    def __init__(self, result: PersistSuccessfulLlmDispatchArtifactsResult) -> None:
        self.result = result
        self.commands: list[PersistSuccessfulLlmDispatchArtifactsCommand] = []

    async def execute(
        self,
        command: PersistSuccessfulLlmDispatchArtifactsCommand,
    ) -> PersistSuccessfulLlmDispatchArtifactsResult:
        self.commands.append(command)
        return self.result


def _started_at() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 6, 11, 12, 1, tzinfo=UTC)


def _artifact_created_at() -> datetime:
    return datetime(2026, 6, 11, 12, 2, tzinfo=UTC)


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


def _work_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("execution.test"),
        status=WorkItemStatus.COMPLETED,
    )


def _outcome_result() -> RecordWorkItemAttemptOutcomeResult:
    return RecordWorkItemAttemptOutcomeResult(work_item=_work_item())


def _llm_success() -> LlmDispatchExecutionResult:
    return LlmDispatchExecutionResult(
        status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_finished_at(),
        output_payload={"raw_text": "{}"},
    )


def _llm_failure() -> LlmDispatchExecutionResult:
    return LlmDispatchExecutionResult(
        status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
        finished_at=_finished_at(),
        error_kind="invalid_dispatch_payload",
    )


def _llm_deferred() -> LlmDispatchExecutionResult:
    return LlmDispatchExecutionResult(
        status=LlmDispatchExecutionStatus.DEFERRED,
        finished_at=_finished_at(),
        error_kind="minute_limit",
        next_attempt_at=datetime(2026, 6, 11, 12, 5, tzinfo=UTC),
    )


def _execution_result(
    llm_result: LlmDispatchExecutionResult,
) -> ExecutePreparedLlmDispatchAttemptResult:
    return ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=llm_result,
        outcome_result=_outcome_result(),
    )


def _artifact_result() -> PersistSuccessfulLlmDispatchArtifactsResult:
    return PersistSuccessfulLlmDispatchArtifactsResult(
        artifacts=(ArtifactRef("llm-dispatch-output:attempt-1"),),
    )


def _runner(
    *,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    artifact_result: PersistSuccessfulLlmDispatchArtifactsResult | None = None,
) -> tuple[
    ExecutePreparedLlmDispatchAttemptWithArtifacts,
    FakeExecutePreparedLlmDispatchAttempt,
    FakePersistSuccessfulLlmDispatchArtifacts,
]:
    execute_attempt = FakeExecutePreparedLlmDispatchAttempt(result=execution_result)
    persist_artifacts = FakePersistSuccessfulLlmDispatchArtifacts(
        result=artifact_result if artifact_result is not None else _artifact_result(),
    )
    return (
        ExecutePreparedLlmDispatchAttemptWithArtifacts(
            execute_attempt=cast(ExecutePreparedLlmDispatchAttempt, execute_attempt),
            persist_success_artifacts=cast(
                PersistSuccessfulLlmDispatchArtifacts,
                persist_artifacts,
            ),
        ),
        execute_attempt,
        persist_artifacts,
    )


@pytest.mark.asyncio
async def test_success_execution_persists_artifacts() -> None:
    runner, execute_attempt, persist_artifacts = _runner(
        execution_result=_execution_result(_llm_success()),
        artifact_result=_artifact_result(),
    )

    result = await runner.execute(
        ExecutePreparedLlmDispatchAttemptWithArtifactsCommand(
            attempt_id="attempt-1",
            artifact_created_at=_artifact_created_at(),
        ),
    )

    assert execute_attempt.commands == [
        ExecutePreparedLlmDispatchAttemptCommand(attempt_id="attempt-1"),
    ]
    assert len(persist_artifacts.commands) == 1
    assert result.artifact_result == _artifact_result()


@pytest.mark.asyncio
async def test_non_success_execution_does_not_persist_artifacts() -> None:
    runner, _, persist_artifacts = _runner(
        execution_result=_execution_result(_llm_failure()),
    )

    result = await runner.execute(
        ExecutePreparedLlmDispatchAttemptWithArtifactsCommand(
            attempt_id="attempt-1",
            artifact_created_at=_artifact_created_at(),
        ),
    )

    assert persist_artifacts.commands == []
    assert result.artifact_result is None


@pytest.mark.asyncio
async def test_artifact_command_receives_exact_dispatch_and_llm_result() -> None:
    execution_result = _execution_result(_llm_success())
    runner, _, persist_artifacts = _runner(execution_result=execution_result)

    await runner.execute(
        ExecutePreparedLlmDispatchAttemptWithArtifactsCommand(
            attempt_id="attempt-1",
            artifact_created_at=_artifact_created_at(),
        ),
    )

    assert persist_artifacts.commands == [
        PersistSuccessfulLlmDispatchArtifactsCommand(
            dispatch=execution_result.dispatch,
            llm_result=execution_result.llm_result,
            created_at=_artifact_created_at(),
        ),
    ]


@pytest.mark.asyncio
async def test_result_returns_execution_result_and_artifact_result_on_success() -> None:
    execution_result = _execution_result(_llm_success())
    artifact_result = _artifact_result()
    runner, _, _ = _runner(
        execution_result=execution_result,
        artifact_result=artifact_result,
    )

    result = await runner.execute(
        ExecutePreparedLlmDispatchAttemptWithArtifactsCommand(
            attempt_id="attempt-1",
            artifact_created_at=_artifact_created_at(),
        ),
    )

    assert result.execution_result == execution_result
    assert result.artifact_result == artifact_result


@pytest.mark.asyncio
async def test_result_returns_none_artifact_result_on_deferred() -> None:
    execution_result = _execution_result(_llm_deferred())
    runner, _, persist_artifacts = _runner(execution_result=execution_result)

    result = await runner.execute(
        ExecutePreparedLlmDispatchAttemptWithArtifactsCommand(
            attempt_id="attempt-1",
            artifact_created_at=_artifact_created_at(),
        ),
    )

    assert result.execution_result == execution_result
    assert result.artifact_result is None
    assert persist_artifacts.commands == []


def test_naive_artifact_created_at_rejected() -> None:
    with pytest.raises(ValueError, match="artifact_created_at"):
        ExecutePreparedLlmDispatchAttemptWithArtifactsCommand(
            attempt_id="attempt-1",
            artifact_created_at=datetime(2026, 6, 11, 12, 2),
        )


def test_empty_attempt_id_rejected() -> None:
    with pytest.raises(ValueError, match="attempt_id"):
        ExecutePreparedLlmDispatchAttemptWithArtifactsCommand(
            attempt_id=" ",
            artifact_created_at=_artifact_created_at(),
        )
