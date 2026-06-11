from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.contexts.workflow_runtime.application.ports.command_log_repository_port import (
    CommandLogRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.event_cursor_repository_port import (
    EventCursorRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.outbox_repository_port import (
    OutboxRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.progress_snapshot_repository_port import (
    ProgressSnapshotRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.resource_usage_repository_port import (
    ResourceUsageRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.timeline_repository_port import (
    TimelineRepositoryPort,
)


@runtime_checkable
class WorkflowRuntimeUnitOfWorkPort(Protocol):
    @property
    def command_log(self) -> CommandLogRepositoryPort: ...

    @property
    def outbox(self) -> OutboxRepositoryPort: ...

    @property
    def event_cursors(self) -> EventCursorRepositoryPort: ...

    @property
    def progress_snapshots(self) -> ProgressSnapshotRepositoryPort: ...

    @property
    def timeline(self) -> TimelineRepositoryPort: ...

    @property
    def resource_usage(self) -> ResourceUsageRepositoryPort: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
