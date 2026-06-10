from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem


class WorkItemSchedulingUnitOfWorkPort(Protocol):
    """Async transaction boundary for idempotent Execution Runtime scheduling."""

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        """Return a scheduled work item by deterministic identity."""

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        """Return persisted schedule payload hash for idempotency checks."""

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: Mapping[str, object],
    ) -> None:
        """Persist a newly scheduled READY work item and scheduling metadata."""

    async def commit(self) -> None:
        """Commit transaction."""

    async def rollback(self) -> None:
        """Rollback transaction."""
