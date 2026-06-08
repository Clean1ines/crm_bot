from __future__ import annotations

from typing import Protocol, TypeAlias

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemCancelled,
    WorkItemCompleted,
    WorkItemDeferred,
    WorkItemFailed,
    WorkItemLeaseExpired,
    WorkItemLeased,
    WorkItemSplitSuperseded,
    WorkItemUserActionRequired,
    WorkItemUserActionResolved,
)


WorkItemEvent: TypeAlias = (
    WorkItemLeased
    | WorkItemCompleted
    | WorkItemDeferred
    | WorkItemFailed
    | WorkItemCancelled
    | WorkItemLeaseExpired
    | WorkItemSplitSuperseded
    | WorkItemUserActionRequired
    | WorkItemUserActionResolved
)


class WorkItemUnitOfWorkPort(Protocol):
    """Transaction boundary for Execution Runtime work item lifecycle changes."""

    def save_work_item(self, item: WorkItem) -> None:
        """Persist updated work item state."""

    def save_attempt(self, attempt: WorkItemAttempt) -> None:
        """Persist a work item attempt record."""

    def append_event(self, event: WorkItemEvent) -> None:
        """Append a durable event to be committed with the state change."""

    def commit(self) -> None:
        """Commit transaction."""

    def rollback(self) -> None:
        """Rollback transaction."""
