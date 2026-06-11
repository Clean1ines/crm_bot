from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
)


@runtime_checkable
class ResourceUsageRepositoryPort(Protocol):
    async def get_usage(
        self,
        workflow_run_id: str,
    ) -> WorkflowResourceUsageSnapshot | None: ...

    async def save_usage(
        self,
        usage: WorkflowResourceUsageSnapshot,
    ) -> WorkflowResourceUsageSnapshot: ...
