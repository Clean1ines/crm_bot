from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemCompleted,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)


@dataclass(frozen=True, slots=True)
class CompleteWorkItemCommand:
    item: WorkItem
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CompleteWorkItemResult:
    item: WorkItem
    event: WorkItemCompleted


class CompleteWorkItem:
    """Complete a leased work item and commit the lifecycle event atomically."""

    def __init__(self, *, unit_of_work: WorkItemUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, command: CompleteWorkItemCommand) -> CompleteWorkItemResult:
        completed_item = WorkItemStateMachine.complete_leased(command.item)
        event = WorkItemCompleted(
            work_item_id=completed_item.work_item_id,
            occurred_at=command.occurred_at,
        )

        try:
            self._unit_of_work.save_work_item(completed_item)
            self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return CompleteWorkItemResult(item=completed_item, event=event)
