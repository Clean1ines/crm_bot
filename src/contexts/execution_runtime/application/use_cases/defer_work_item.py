from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemDeferred,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil


@dataclass(frozen=True, slots=True)
class DeferWorkItemCommand:
    item: WorkItem
    wait_until: WaitUntil
    occurred_at: datetime
    error_kind: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.error_kind is not None and not self.error_kind.strip():
            raise ValueError("error_kind must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class DeferWorkItemResult:
    item: WorkItem
    event: WorkItemDeferred


class DeferWorkItem:
    """Defer a leased work item and commit the lifecycle event atomically."""

    def __init__(self, *, unit_of_work: WorkItemUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, command: DeferWorkItemCommand) -> DeferWorkItemResult:
        deferred_item = WorkItemStateMachine.defer_leased(
            command.item,
            wait_until=command.wait_until,
            error_kind=command.error_kind,
        )
        event = WorkItemDeferred(
            work_item_id=deferred_item.work_item_id,
            wait_until=command.wait_until.value,
            error_kind=command.error_kind,
            occurred_at=command.occurred_at,
        )

        try:
            self._unit_of_work.save_work_item(deferred_item)
            self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return DeferWorkItemResult(item=deferred_item, event=event)
