from __future__ import annotations

from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem


class WorkItemSplitSupersedeRepositoryPort(Protocol):
    async def load_work_item(self, work_item_id: str) -> WorkItem | None: ...

    async def save_work_item(self, item: WorkItem) -> None: ...
