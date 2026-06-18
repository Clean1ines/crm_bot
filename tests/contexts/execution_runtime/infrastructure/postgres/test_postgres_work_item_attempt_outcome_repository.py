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
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_outcome_repository import (
    PostgresWorkItemAttemptOutcomeRepository,
)


class FakeConnection:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        attempt_update_result: str = "UPDATE 1",
        work_item_update_result: str = "UPDATE 1",
    ) -> None:
        self.row = row
        self.attempt_update_result = attempt_update_result
        self.work_item_update_result = work_item_update_result
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.commit_count = 0
        self.rollback_count = 0

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.row

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        if "UPDATE execution_work_item_attempts" in query:
            return self.attempt_update_result
        if "UPDATE execution_work_items" in query:
            return self.work_item_update_result
        raise AssertionError(f"Unexpected query: {query}")

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def _finished_at() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _next_attempt_at() -> datetime:
    return _finished_at() + timedelta(minutes=5)


def _leased_row(
    *,
    status: str = "leased",
    lease_token: str | None = "lease-token-1",
    attempt_count: int = 1,
) -> dict[str, object]:
    return {
        "work_item_id": "work-1",
        "work_kind": "execution.test",
        "status": status,
        "attempt_count": attempt_count,
        "leased_by": "worker-1" if status == "leased" else None,
        "lease_token": lease_token if status == "leased" else None,
        "lease_expires_at": _finished_at() + timedelta(minutes=10)
        if status == "leased"
        else None,
        "next_attempt_at": None,
        "last_error_kind": None,
        "retry_plan": None,
    }


def _record(
    *,
    outcome_status: WorkItemAttemptOutcomeStatus = (
        WorkItemAttemptOutcomeStatus.SUCCEEDED
    ),
    lease_token: LeaseToken | None = None,
    attempt_number: int = 1,
    error_kind: str | None = None,
    next_attempt_at: datetime | None = None,
    validation_metadata: dict[str, object] | None = None,
    retry_plan: WorkItemRetryPlan | None = None,
) -> WorkItemAttemptOutcomeRecord:
    return WorkItemAttemptOutcomeRecord(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=attempt_number,
        lease_token=lease_token or LeaseToken("lease-token-1"),
        finished_at=_finished_at(),
        outcome_status=outcome_status,
        error_kind=error_kind,
        next_attempt_at=next_attempt_at,
        retry_plan=retry_plan,
        validation_metadata=validation_metadata,
    )


async def _execute(
    connection: FakeConnection,
    record: WorkItemAttemptOutcomeRecord,
):
    return await PostgresWorkItemAttemptOutcomeRepository(
        connection=connection,
    ).record_attempt_outcome(record)


def _attempt_update_args(connection: FakeConnection) -> tuple[object, ...]:
    for query, args in connection.execute_calls:
        if "UPDATE execution_work_item_attempts" in query:
            return args
    raise AssertionError("attempt update was not executed")


def _work_item_update_args(connection: FakeConnection) -> tuple[object, ...]:
    for query, args in connection.execute_calls:
        if "UPDATE execution_work_items" in query:
            return args
    raise AssertionError("work item update was not executed")


@pytest.mark.asyncio
async def test_succeeded_updates_attempt_and_completes_work_item() -> None:
    connection = FakeConnection(row=_leased_row())

    work_item = await _execute(connection, _record())

    assert work_item.status is WorkItemStatus.COMPLETED
    assert work_item.lease_token is None
    assert _attempt_update_args(connection) == (
        "attempt-1",
        _finished_at(),
        "succeeded",
        None,
        None,
        "work-1",
        1,
    )
    work_item_args = _work_item_update_args(connection)
    assert work_item_args[1] == "completed"
    assert work_item_args[3] is None
    assert work_item_args[4] is None
    assert work_item_args[5] is None
    assert work_item_args[6] is None
    assert work_item_args[8] is None


@pytest.mark.asyncio
async def test_succeeded_updates_attempt_with_validation_metadata() -> None:
    connection = FakeConnection(row=_leased_row())

    work_item = await _execute(
        connection,
        _record(
            validation_metadata={
                "draft_claim_compaction_validation_decision": "valid_output",
                "expected_output_kind": "compacted_claims",
            },
        ),
    )

    assert work_item.status is WorkItemStatus.COMPLETED
    assert _attempt_update_args(connection) == (
        "attempt-1",
        _finished_at(),
        "succeeded",
        None,
        (
            '{"draft_claim_compaction_validation_decision": "valid_output", '
            '"expected_output_kind": "compacted_claims"}'
        ),
        "work-1",
        1,
    )


@pytest.mark.asyncio
async def test_retryable_failed_updates_attempt_and_moves_work_item_to_retryable() -> (
    None
):
    connection = FakeConnection(row=_leased_row())

    work_item = await _execute(
        connection,
        _record(
            outcome_status=WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED,
            error_kind="rate_limit",
            next_attempt_at=_next_attempt_at(),
            retry_plan=WorkItemRetryPlan.RETRY_OTHER_ORG,
        ),
    )

    assert work_item.status is WorkItemStatus.RETRYABLE_FAILED
    assert work_item.last_error_kind == "rate_limit"
    assert work_item.retry_plan is WorkItemRetryPlan.RETRY_OTHER_ORG
    assert _attempt_update_args(connection)[2:5] == (
        "retryable_failed",
        "rate_limit",
        None,
    )
    work_item_args = _work_item_update_args(connection)
    assert work_item_args[1] == "retryable_failed"
    assert work_item_args[6] == _next_attempt_at()
    assert work_item_args[7] == "rate_limit"
    assert work_item_args[8] == WorkItemRetryPlan.RETRY_OTHER_ORG.value


@pytest.mark.asyncio
async def test_terminal_failed_updates_attempt_and_moves_work_item_to_terminal() -> (
    None
):
    connection = FakeConnection(row=_leased_row())

    work_item = await _execute(
        connection,
        _record(
            outcome_status=WorkItemAttemptOutcomeStatus.TERMINAL_FAILED,
            error_kind="schema_error",
        ),
    )

    assert work_item.status is WorkItemStatus.TERMINAL_FAILED
    assert work_item.last_error_kind == "schema_error"
    assert _attempt_update_args(connection)[2:5] == (
        "terminal_failed",
        "schema_error",
        None,
    )
    work_item_args = _work_item_update_args(connection)
    assert work_item_args[1] == "terminal_failed"
    assert work_item_args[6] is None
    assert work_item_args[7] == "schema_error"


@pytest.mark.asyncio
async def test_deferred_updates_attempt_and_next_attempt_at() -> None:
    connection = FakeConnection(row=_leased_row())

    work_item = await _execute(
        connection,
        _record(
            outcome_status=WorkItemAttemptOutcomeStatus.DEFERRED,
            error_kind="quota_wait",
            next_attempt_at=_next_attempt_at(),
            retry_plan=WorkItemRetryPlan.WAIT_NEAREST_CAPACITY_WINDOW,
        ),
    )

    assert work_item.status is WorkItemStatus.RETRYABLE_FAILED
    assert work_item.last_error_kind == "quota_wait"
    assert work_item.retry_plan is WorkItemRetryPlan.WAIT_NEAREST_CAPACITY_WINDOW
    assert _attempt_update_args(connection)[2:5] == (
        "deferred",
        "quota_wait",
        None,
    )
    work_item_args = _work_item_update_args(connection)
    assert work_item_args[1] == "retryable_failed"
    assert work_item_args[6] == _next_attempt_at()
    assert work_item_args[7] == "quota_wait"
    assert work_item_args[8] == WorkItemRetryPlan.WAIT_NEAREST_CAPACITY_WINDOW.value


@pytest.mark.asyncio
async def test_lease_token_mismatch_raises() -> None:
    connection = FakeConnection(row=_leased_row())

    with pytest.raises(ValueError, match="lease_token"):
        await _execute(
            connection,
            _record(lease_token=LeaseToken("different-token")),
        )

    assert connection.execute_calls == []


@pytest.mark.asyncio
async def test_attempt_number_mismatch_raises() -> None:
    connection = FakeConnection(row=_leased_row(attempt_count=2))

    with pytest.raises(ValueError, match="attempt_number"):
        await _execute(connection, _record(attempt_number=1))

    assert connection.execute_calls == []


@pytest.mark.asyncio
async def test_non_leased_work_item_raises() -> None:
    connection = FakeConnection(row=_leased_row(status="ready"))

    with pytest.raises(ValueError, match="leased"):
        await _execute(connection, _record())

    assert connection.execute_calls == []


@pytest.mark.asyncio
async def test_no_attempt_row_updated_raises() -> None:
    connection = FakeConnection(
        row=_leased_row(),
        attempt_update_result="UPDATE 0",
    )

    with pytest.raises(RuntimeError, match="attempt outcome update"):
        await _execute(connection, _record())


@pytest.mark.asyncio
async def test_no_work_item_row_updated_raises() -> None:
    connection = FakeConnection(
        row=_leased_row(),
        work_item_update_result="UPDATE 0",
    )

    with pytest.raises(RuntimeError, match="work item outcome update"):
        await _execute(connection, _record())


@pytest.mark.asyncio
async def test_repository_does_not_commit_or_rollback() -> None:
    connection = FakeConnection(row=_leased_row())

    await _execute(connection, _record())

    assert connection.commit_count == 0
    assert connection.rollback_count == 0


def test_repository_has_no_llm_or_capacity_runtime_imports() -> None:
    from pathlib import Path

    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_outcome_repository.py",
    ).read_text(encoding="utf-8")

    assert "llm_runtime" not in source
    assert "capacity_runtime" not in source
