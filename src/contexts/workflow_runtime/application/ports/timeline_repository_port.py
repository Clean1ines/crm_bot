from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
)


@runtime_checkable
class TimelineRepositoryPort(Protocol):
    async def append_entry(
        self,
        entry: WorkflowTimelineEntry,
    ) -> WorkflowTimelineEntry: ...

    async def list_recent_entries(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowTimelineEntry, ...]: ...
