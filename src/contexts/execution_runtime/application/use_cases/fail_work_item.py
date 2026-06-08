from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import WorkItemFailed
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


class WorkItemFailureMode(StrEnum):
    RETRYABLE = "retryable"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class FailWorkItemCommand:
    item: WorkItem
    mode: WorkItemFailureMode
    error_kind: str
    occurred_at: datetime
    next_attempt_at: WaitUntil | None = None

    def __post_init__(self) -> None:
        if not self.error_kind or not self.error_kind.strip():
            raise ValueError("error_kind must be non-empty")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.mode is WorkItemFailureMode.RETRYABLE and self.next_attempt_at is None:
            raise ValueError("retryable failure requires next_attempt_at")
        if (
            self.mode is WorkItemFailureMode.TERMINAL
            and self.next_attempt_at is not None
        ):
            raise ValueError("terminal failure must not have next_attempt_at")


@dataclass(frozen=True, slots=True)
class FailWorkItemResult:
    item: WorkItem
    event: WorkItemFailed


class FailWorkItem:
    """Fail a leased work item and commit the lifecycle event atomically."""

    def __init__(self, *, unit_of_work: WorkItemUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, command: FailWorkItemCommand) -> FailWorkItemResult:
        if command.mode is WorkItemFailureMode.RETRYABLE:
            if command.next_attempt_at is None:
                raise ValueError("retryable failure requires next_attempt_at")
            failed_item = WorkItemStateMachine.fail_leased_retryable(
                command.item,
                error_kind=command.error_kind,
                next_attempt_at=command.next_attempt_at,
            )
        else:
            failed_item = WorkItemStateMachine.fail_leased_terminal(
                command.item,
                error_kind=command.error_kind,
            )

        event = WorkItemFailed(
            work_item_id=failed_item.work_item_id,
            status=WorkItemStatus(failed_item.status),
            error_kind=command.error_kind,
            occurred_at=command.occurred_at,
        )

        try:
            self._unit_of_work.save_work_item(failed_item)
            self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return FailWorkItemResult(item=failed_item, event=event)
