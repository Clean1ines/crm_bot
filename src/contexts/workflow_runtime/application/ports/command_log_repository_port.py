from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)


@runtime_checkable
class CommandLogRepositoryPort(Protocol):
    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand: ...

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand: ...
