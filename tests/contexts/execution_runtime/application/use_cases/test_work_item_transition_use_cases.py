from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemEvent,
)
from src.contexts.execution_runtime.application.use_cases.cancel_work_item import (
    CancelWorkItem,
    CancelWorkItemCommand,
)
from src.contexts.execution_runtime.application.use_cases.complete_work_item import (
    CompleteWorkItem,
    CompleteWorkItemCommand,
)
from src.contexts.execution_runtime.application.use_cases.defer_work_item import (
    DeferWorkItem,
    DeferWorkItemCommand,
)
from src.contexts.execution_runtime.application.use_cases.fail_work_item import (
    FailWorkItem,
    FailWorkItemCommand,
    WorkItemFailureMode,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemCancelled,
    WorkItemCompleted,
    WorkItemDeferred,
    WorkItemFailed,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(slots=True)
class FakeWorkItemUnitOfWork:
    saved_items: list[WorkItem] = field(default_factory=list)
    saved_attempts: list[WorkItemAttempt] = field(default_factory=list)
    appended_events: list[WorkItemEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False
    fail_on_commit: bool = False

    def save_work_item(self, item: WorkItem) -> None:
        self.actions.append("save_work_item")
        self.saved_items.append(item)

    def save_attempt(self, attempt: WorkItemAttempt) -> None:
        self.actions.append("save_attempt")
        self.saved_attempts.append(attempt)

    def append_event(self, event: WorkItemEvent) -> None:
        self.actions.append("append_event")
        self.appended_events.append(event)

    def commit(self) -> None:
        self.actions.append("commit")
        if self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    def rollback(self) -> None:
        self.actions.append("rollback")
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _ready_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
    )


def _leased_item() -> WorkItem:
    now = _now()
    return WorkItemStateMachine.lease_ready(
        _ready_item(),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )


def _assert_transition_committed(unit_of_work: FakeWorkItemUnitOfWork) -> None:
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_work_item",
        "append_event",
        "commit",
    ]


def test_complete_work_item_commits_completed_item_and_event() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()

    result = CompleteWorkItem(unit_of_work=unit_of_work).execute(
        CompleteWorkItemCommand(
            item=_leased_item(),
            occurred_at=_now(),
        ),
    )

    assert result.item.status is WorkItemStatus.COMPLETED
    assert isinstance(result.event, WorkItemCompleted)
    assert unit_of_work.saved_items == [result.item]
    assert unit_of_work.appended_events == [result.event]
    _assert_transition_committed(unit_of_work)


def test_defer_work_item_commits_deferred_item_and_event() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()
    wait_until = WaitUntil(_now() + timedelta(seconds=60))

    result = DeferWorkItem(unit_of_work=unit_of_work).execute(
        DeferWorkItemCommand(
            item=_leased_item(),
            wait_until=wait_until,
            error_kind="minute_limit",
            occurred_at=_now(),
        ),
    )

    assert result.item.status is WorkItemStatus.DEFERRED
    assert result.item.next_attempt_at == wait_until
    assert result.item.last_error_kind == "minute_limit"
    assert isinstance(result.event, WorkItemDeferred)
    assert result.event.wait_until == wait_until.value
    assert result.event.error_kind == "minute_limit"
    _assert_transition_committed(unit_of_work)


def test_fail_work_item_commits_retryable_failure() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()
    next_attempt_at = WaitUntil(_now() + timedelta(seconds=10))

    result = FailWorkItem(unit_of_work=unit_of_work).execute(
        FailWorkItemCommand(
            item=_leased_item(),
            mode=WorkItemFailureMode.RETRYABLE,
            error_kind="network_error",
            next_attempt_at=next_attempt_at,
            occurred_at=_now(),
        ),
    )

    assert result.item.status is WorkItemStatus.RETRYABLE_FAILED
    assert result.item.next_attempt_at == next_attempt_at
    assert result.item.last_error_kind == "network_error"
    assert isinstance(result.event, WorkItemFailed)
    assert result.event.status is WorkItemStatus.RETRYABLE_FAILED
    _assert_transition_committed(unit_of_work)


def test_fail_work_item_commits_terminal_failure() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()

    result = FailWorkItem(unit_of_work=unit_of_work).execute(
        FailWorkItemCommand(
            item=_leased_item(),
            mode=WorkItemFailureMode.TERMINAL,
            error_kind="invalid_payload",
            occurred_at=_now(),
        ),
    )

    assert result.item.status is WorkItemStatus.TERMINAL_FAILED
    assert result.item.next_attempt_at is None
    assert result.item.last_error_kind == "invalid_payload"
    assert isinstance(result.event, WorkItemFailed)
    assert result.event.status is WorkItemStatus.TERMINAL_FAILED
    _assert_transition_committed(unit_of_work)


def test_cancel_work_item_commits_cancelled_item_and_event() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()

    result = CancelWorkItem(unit_of_work=unit_of_work).execute(
        CancelWorkItemCommand(
            item=_leased_item(),
            reason="cancelled_by_user",
            occurred_at=_now(),
        ),
    )

    assert result.item.status is WorkItemStatus.CANCELLED
    assert result.item.last_error_kind == "cancelled_by_user"
    assert isinstance(result.event, WorkItemCancelled)
    assert result.event.reason == "cancelled_by_user"
    _assert_transition_committed(unit_of_work)


def test_transition_use_case_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeWorkItemUnitOfWork(fail_on_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        CompleteWorkItem(unit_of_work=unit_of_work).execute(
            CompleteWorkItemCommand(
                item=_leased_item(),
                occurred_at=_now(),
            ),
        )

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_work_item",
        "append_event",
        "commit",
        "rollback",
    ]


def test_commands_validate_timestamps_and_required_failure_fields() -> None:
    naive = datetime(2026, 6, 8, 12, 0)

    with pytest.raises(ValueError):
        CompleteWorkItemCommand(item=_leased_item(), occurred_at=naive)

    with pytest.raises(ValueError):
        DeferWorkItemCommand(
            item=_leased_item(),
            wait_until=WaitUntil(_now() + timedelta(seconds=60)),
            occurred_at=naive,
        )

    with pytest.raises(ValueError):
        FailWorkItemCommand(
            item=_leased_item(),
            mode=WorkItemFailureMode.RETRYABLE,
            error_kind="network_error",
            occurred_at=_now(),
        )

    with pytest.raises(ValueError):
        FailWorkItemCommand(
            item=_leased_item(),
            mode=WorkItemFailureMode.TERMINAL,
            error_kind="network_error",
            next_attempt_at=WaitUntil(_now() + timedelta(seconds=10)),
            occurred_at=_now(),
        )

    with pytest.raises(ValueError):
        CancelWorkItemCommand(
            item=_leased_item(),
            reason="",
            occurred_at=_now(),
        )
