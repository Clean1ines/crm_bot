from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemEvent,
)
from src.contexts.execution_runtime.application.use_cases.reclaim_expired_leases import (
    ReclaimExpiredLeases,
    ReclaimExpiredLeasesCommand,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemLeaseExpired,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
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


def _ready_item(work_item_id: str = "work-1") -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
    )


def _leased_item(
    *,
    work_item_id: str = "work-1",
    lease_expires_delta: timedelta = timedelta(seconds=30),
) -> WorkItem:
    now = _now()
    return WorkItemStateMachine.lease_ready(
        _ready_item(work_item_id),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken(f"lease-{work_item_id}"),
        lease_expires_at=now + lease_expires_delta,
        now=now,
    )


def test_reclaim_expired_leases_commits_only_expired_leased_items() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()
    expired = _leased_item(
        work_item_id="expired-work",
        lease_expires_delta=timedelta(seconds=30),
    )
    active = _leased_item(
        work_item_id="active-work",
        lease_expires_delta=timedelta(seconds=90),
    )
    ready = _ready_item("ready-work")

    result = ReclaimExpiredLeases(unit_of_work=unit_of_work).execute(
        ReclaimExpiredLeasesCommand(
            items=(expired, active, ready),
            now=_now() + timedelta(seconds=30),
        ),
    )

    assert result.reclaimed_count == 1
    assert result.reclaimed_items[0].work_item_id == "expired-work"
    assert result.reclaimed_items[0].status is WorkItemStatus.READY
    assert result.reclaimed_items[0].last_error_kind == "lease_expired"
    assert result.reclaimed_items[0].leased_by is None
    assert result.reclaimed_items[0].lease_token is None
    assert result.reclaimed_items[0].lease_expires_at is None

    assert len(result.events) == 1
    assert isinstance(result.events[0], WorkItemLeaseExpired)
    assert result.events[0].work_item_id == "expired-work"
    assert result.events[0].previous_worker_ref == "worker-1"

    assert unit_of_work.saved_items == [result.reclaimed_items[0]]
    assert unit_of_work.appended_events == [result.events[0]]
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_work_item",
        "append_event",
        "commit",
    ]


def test_reclaim_expired_leases_does_not_commit_when_nothing_changed() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()
    active = _leased_item(
        work_item_id="active-work",
        lease_expires_delta=timedelta(seconds=90),
    )

    result = ReclaimExpiredLeases(unit_of_work=unit_of_work).execute(
        ReclaimExpiredLeasesCommand(
            items=(active, _ready_item("ready-work")),
            now=_now() + timedelta(seconds=30),
        ),
    )

    assert result.reclaimed_count == 0
    assert result.reclaimed_items == ()
    assert result.events == ()
    assert unit_of_work.actions == []
    assert not unit_of_work.committed
    assert not unit_of_work.rolled_back


def test_reclaim_expired_leases_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeWorkItemUnitOfWork(fail_on_commit=True)
    expired = _leased_item(
        work_item_id="expired-work",
        lease_expires_delta=timedelta(seconds=30),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        ReclaimExpiredLeases(unit_of_work=unit_of_work).execute(
            ReclaimExpiredLeasesCommand(
                items=(expired,),
                now=_now() + timedelta(seconds=30),
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


def test_reclaim_expired_leases_command_requires_timezone_aware_now() -> None:
    with pytest.raises(ValueError):
        ReclaimExpiredLeasesCommand(
            items=(),
            now=datetime(2026, 6, 8, 12, 0),
        )
