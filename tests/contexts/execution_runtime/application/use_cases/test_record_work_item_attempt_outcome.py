from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.contexts.execution_runtime.application.ports.work_item_attempt_outcome_repository_port import (
    WorkItemAttemptOutcomeRecord,
    WorkItemAttemptOutcomeStatus,
)
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcome,
    RecordWorkItemAttemptOutcomeCommand,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)


class FakeRepository:
    def __init__(self, work_item: WorkItem) -> None:
        self.work_item = work_item
        self.records: list[WorkItemAttemptOutcomeRecord] = []

    async def record_attempt_outcome(
        self,
        record: WorkItemAttemptOutcomeRecord,
    ) -> WorkItem:
        self.records.append(record)
        return self.work_item


def _finished_at() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _next_attempt_at() -> datetime:
    return _finished_at() + timedelta(minutes=5)


def _lease_token() -> LeaseToken:
    return LeaseToken("lease-token-1")


def _work_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("execution.test"),
    )


def _command(
    *,
    finished_at: datetime | None = None,
    outcome_status: WorkItemAttemptOutcomeStatus = (
        WorkItemAttemptOutcomeStatus.SUCCEEDED
    ),
    error_kind: str | None = None,
    next_attempt_at: datetime | None = None,
    retry_plan: WorkItemRetryPlan | None = None,
) -> RecordWorkItemAttemptOutcomeCommand:
    return RecordWorkItemAttemptOutcomeCommand(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        lease_token=_lease_token(),
        finished_at=finished_at or _finished_at(),
        outcome_status=outcome_status,
        error_kind=error_kind,
        next_attempt_at=next_attempt_at,
        retry_plan=retry_plan,
    )


@pytest.mark.asyncio
async def test_success_delegates_and_returns_work_item() -> None:
    repository = FakeRepository(work_item=_work_item())

    result = await RecordWorkItemAttemptOutcome(repository=repository).execute(
        _command(),
    )

    assert result.work_item == repository.work_item
    assert repository.records == [
        WorkItemAttemptOutcomeRecord(
            attempt_id="attempt-1",
            work_item_id="work-1",
            attempt_number=1,
            lease_token=_lease_token(),
            finished_at=_finished_at(),
            outcome_status=WorkItemAttemptOutcomeStatus.SUCCEEDED,
        ),
    ]


@pytest.mark.asyncio
async def test_rejects_naive_finished_at() -> None:
    repository = FakeRepository(work_item=_work_item())

    with pytest.raises(ValueError, match="finished_at"):
        await RecordWorkItemAttemptOutcome(repository=repository).execute(
            _command(finished_at=datetime(2026, 6, 11, 12, 0)),
        )


@pytest.mark.asyncio
async def test_rejects_succeeded_with_error_kind() -> None:
    repository = FakeRepository(work_item=_work_item())

    with pytest.raises(ValueError, match="error_kind"):
        await RecordWorkItemAttemptOutcome(repository=repository).execute(
            _command(error_kind="boom"),
        )


@pytest.mark.asyncio
async def test_rejects_failed_without_error_kind() -> None:
    repository = FakeRepository(work_item=_work_item())

    with pytest.raises(ValueError, match="error_kind"):
        await RecordWorkItemAttemptOutcome(repository=repository).execute(
            _command(
                outcome_status=WorkItemAttemptOutcomeStatus.TERMINAL_FAILED,
            ),
        )


@pytest.mark.asyncio
async def test_retryable_without_next_attempt_at_is_immediate_retry() -> None:
    repository = FakeRepository(work_item=_work_item())

    result = await RecordWorkItemAttemptOutcome(repository=repository).execute(
        _command(
            outcome_status=WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED,
            error_kind="validation_failed",
            retry_plan=WorkItemRetryPlan.RETRY_SAME_ROUTE,
        ),
    )

    assert result.work_item == repository.work_item
    assert repository.records[0].next_attempt_at is None


@pytest.mark.asyncio
async def test_rejects_retryable_without_retry_plan() -> None:
    repository = FakeRepository(work_item=_work_item())

    with pytest.raises(ValueError, match="retry_plan"):
        await RecordWorkItemAttemptOutcome(repository=repository).execute(
            _command(
                outcome_status=WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED,
                error_kind="validation_failed",
            ),
        )


@pytest.mark.asyncio
async def test_rejects_deferred_without_next_attempt_at() -> None:
    repository = FakeRepository(work_item=_work_item())

    with pytest.raises(ValueError, match="next_attempt_at"):
        await RecordWorkItemAttemptOutcome(repository=repository).execute(
            _command(
                outcome_status=WorkItemAttemptOutcomeStatus.DEFERRED,
                error_kind="not_ready",
            ),
        )


@pytest.mark.asyncio
async def test_rejects_next_attempt_at_not_after_finished_at() -> None:
    repository = FakeRepository(work_item=_work_item())

    with pytest.raises(ValueError, match="next_attempt_at"):
        await RecordWorkItemAttemptOutcome(repository=repository).execute(
            _command(
                outcome_status=WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED,
                error_kind="rate_limit",
                next_attempt_at=_finished_at(),
                retry_plan=WorkItemRetryPlan.RETRY_SAME_ROUTE,
            ),
        )
