from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemLeaseExpired,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


@dataclass(frozen=True, slots=True)
class ReclaimExpiredLeasesCommand:
    items: tuple[WorkItem, ...]
    now: datetime

    def __post_init__(self) -> None:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ReclaimExpiredLeasesResult:
    reclaimed_items: tuple[WorkItem, ...]
    events: tuple[WorkItemLeaseExpired, ...]

    @property
    def reclaimed_count(self) -> int:
        return len(self.reclaimed_items)


class ReclaimExpiredLeases:
    """Reclaim expired leased work items in one transaction.

    Non-leased items and still-active leases are ignored. The use case is generic
    and does not know why the work was running.
    """

    def __init__(self, *, unit_of_work: WorkItemUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    def execute(
        self,
        command: ReclaimExpiredLeasesCommand,
    ) -> ReclaimExpiredLeasesResult:
        reclaimed_items: list[WorkItem] = []
        events: list[WorkItemLeaseExpired] = []

        for item in command.items:
            previous_worker_ref = (
                item.leased_by.value
                if item.status is WorkItemStatus.LEASED and item.leased_by is not None
                else None
            )

            reclaimed_item = WorkItemStateMachine.reclaim_expired_lease(
                item,
                now=command.now,
            )

            if reclaimed_item is item:
                continue

            reclaimed_items.append(reclaimed_item)
            events.append(
                WorkItemLeaseExpired(
                    work_item_id=reclaimed_item.work_item_id,
                    previous_worker_ref=previous_worker_ref,
                    occurred_at=command.now,
                ),
            )

        if not reclaimed_items:
            return ReclaimExpiredLeasesResult(
                reclaimed_items=(),
                events=(),
            )

        try:
            for item in reclaimed_items:
                self._unit_of_work.save_work_item(item)
            for event in events:
                self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return ReclaimExpiredLeasesResult(
            reclaimed_items=tuple(reclaimed_items),
            events=tuple(events),
        )
