from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.application.workbench_commands.manual_resume import (
    WorkbenchManualResumeCommand,
    WorkbenchManualResumeNotFoundError,
    WorkbenchManualResumeRejectedError,
    WorkbenchManualResumeService,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)
from src.infrastructure.queue.workbench_queue import WorkbenchQueueAdapter


class WorkbenchManualResumeDbPool(Protocol):
    async def acquire(self): ...


class WorkbenchManualResumeQueueRepository(Protocol):
    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, object] | None = None,
        max_attempts: int = 3,
    ) -> str: ...


async def resume_workbench_document(
    *,
    pool: WorkbenchManualResumeDbPool,
    queue_repo: WorkbenchManualResumeQueueRepository,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = KnowledgeWorkbenchRepository(connection)
        queue = WorkbenchQueueAdapter(queue_repository=queue_repo)
        service = WorkbenchManualResumeService(repository, queue)
        result = await service.resume_document(
            WorkbenchManualResumeCommand(
                project_id=project_id,
                document_id=document_id,
            )
        )
        return result.to_dict()


__all__ = [
    "WorkbenchManualResumeNotFoundError",
    "WorkbenchManualResumeRejectedError",
    "resume_workbench_document",
]
