from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemCancelled,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)


@dataclass(frozen=True, slots=True)
class CancelWorkItemCommand:
    item: WorkItem
    occurred_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.reason is not None and not self.reason.strip():
            raise ValueError("reason must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class CancelWorkItemResult:
    item: WorkItem
    event: WorkItemCancelled


class CancelWorkItem:
    """Cancel a non-terminal work item and commit the lifecycle event atomically."""

    def __init__(self, *, unit_of_work: WorkItemUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, command: CancelWorkItemCommand) -> CancelWorkItemResult:
        cancelled_item = WorkItemStateMachine.cancel(
            command.item,
            error_kind=command.reason or "cancelled",
        )
        event = WorkItemCancelled(
            work_item_id=cancelled_item.work_item_id,
            reason=command.reason,
            occurred_at=command.occurred_at,
        )

        try:
            self._unit_of_work.save_work_item(cancelled_item)
            self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return CancelWorkItemResult(item=cancelled_item, event=event)
