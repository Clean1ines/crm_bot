from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)


@runtime_checkable
class ProgressSnapshotRepositoryPort(Protocol):
    async def get_snapshot(
        self,
        workflow_run_id: str,
    ) -> WorkflowProgressSnapshot | None: ...

    async def save_snapshot(
        self,
        snapshot: WorkflowProgressSnapshot,
    ) -> WorkflowProgressSnapshot: ...
