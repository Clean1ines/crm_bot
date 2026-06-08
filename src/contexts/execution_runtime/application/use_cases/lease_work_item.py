from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import WorkItemLeased
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(frozen=True, slots=True)
class LeaseWorkItemCommand:
    item: WorkItem
    worker: WorkerRef
    lease_token: LeaseToken
    lease_expires_at: datetime
    now: datetime
    attempt_id: str

    def __post_init__(self) -> None:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if (
            self.lease_expires_at.tzinfo is None
            or self.lease_expires_at.utcoffset() is None
        ):
            raise ValueError("lease_expires_at must be timezone-aware")
        if not self.attempt_id or not self.attempt_id.strip():
            raise ValueError("attempt_id must be non-empty")


@dataclass(frozen=True, slots=True)
class LeaseWorkItemResult:
    item: WorkItem
    attempt: WorkItemAttempt
    event: WorkItemLeased


class LeaseWorkItem:
    """Lease one due work item and commit attempt/event atomically."""

    def __init__(self, *, unit_of_work: WorkItemUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, command: LeaseWorkItemCommand) -> LeaseWorkItemResult:
        leased_item = WorkItemStateMachine.lease_ready(
            command.item,
            worker=command.worker,
            lease_token=command.lease_token,
            lease_expires_at=command.lease_expires_at,
            now=command.now,
        )

        attempt = WorkItemAttempt(
            attempt_id=command.attempt_id,
            work_item_id=leased_item.work_item_id,
            attempt_number=leased_item.attempt_count,
            started_at=command.now,
        )

        event = WorkItemLeased(
            work_item_id=leased_item.work_item_id,
            worker_ref=command.worker.value,
            occurred_at=command.now,
        )

        try:
            self._unit_of_work.save_work_item(leased_item)
            self._unit_of_work.save_attempt(attempt)
            self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return LeaseWorkItemResult(
            item=leased_item,
            attempt=attempt,
            event=event,
        )
