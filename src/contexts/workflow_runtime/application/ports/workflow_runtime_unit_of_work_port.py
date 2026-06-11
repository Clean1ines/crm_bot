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


@runtime_checkable
class WorkflowRuntimeUnitOfWorkPort(Protocol):
    @property
    def command_log(self) -> CommandLogRepositoryPort: ...

    @property
    def outbox(self) -> OutboxRepositoryPort: ...

    @property
    def event_cursors(self) -> EventCursorRepositoryPort: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
