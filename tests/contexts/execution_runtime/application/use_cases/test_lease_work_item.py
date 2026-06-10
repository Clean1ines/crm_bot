from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemEvent,
)
from src.contexts.execution_runtime.application.use_cases.lease_work_item import (
    LeaseWorkItem,
    LeaseWorkItemCommand,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import WorkItemLeased
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
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


def _command(item: WorkItem | None = None) -> LeaseWorkItemCommand:
    now = _now()
    return LeaseWorkItemCommand(
        item=item or _ready_item(),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
        attempt_id="attempt-1",
    )


def test_lease_work_item_commits_item_attempt_and_event() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()

    result = LeaseWorkItem(repository=unit_of_work).execute(_command())

    assert result.item.status is WorkItemStatus.LEASED
    assert result.item.attempt_count == 1
    assert result.item.leased_by == WorkerRef("worker-1")
    assert result.item.lease_token == LeaseToken("lease-1")

    assert result.attempt.attempt_id == "attempt-1"
    assert result.attempt.work_item_id == "work-1"
    assert result.attempt.attempt_number == 1
    assert result.attempt.started_at == _now()

    assert isinstance(result.event, WorkItemLeased)
    assert result.event.work_item_id == "work-1"
    assert result.event.worker_ref == "worker-1"

    assert unit_of_work.saved_items == [result.item]
    assert unit_of_work.saved_attempts == [result.attempt]
    assert unit_of_work.appended_events == [result.event]
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_work_item",
        "save_attempt",
        "append_event",
        "commit",
    ]


def test_lease_work_item_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeWorkItemUnitOfWork(fail_on_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        LeaseWorkItem(repository=unit_of_work).execute(_command())

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_work_item",
        "save_attempt",
        "append_event",
        "commit",
        "rollback",
    ]


def test_lease_work_item_command_requires_valid_timestamps_and_attempt_id() -> None:
    now = _now()

    with pytest.raises(ValueError):
        LeaseWorkItemCommand(
            item=_ready_item(),
            worker=WorkerRef("worker-1"),
            lease_token=LeaseToken("lease-1"),
            lease_expires_at=now + timedelta(seconds=30),
            now=datetime(2026, 6, 8, 12, 0),
            attempt_id="attempt-1",
        )

    with pytest.raises(ValueError):
        LeaseWorkItemCommand(
            item=_ready_item(),
            worker=WorkerRef("worker-1"),
            lease_token=LeaseToken("lease-1"),
            lease_expires_at=datetime(2026, 6, 8, 12, 0),
            now=now,
            attempt_id="attempt-1",
        )

    with pytest.raises(ValueError):
        LeaseWorkItemCommand(
            item=_ready_item(),
            worker=WorkerRef("worker-1"),
            lease_token=LeaseToken("lease-1"),
            lease_expires_at=now + timedelta(seconds=30),
            now=now,
            attempt_id="",
        )
