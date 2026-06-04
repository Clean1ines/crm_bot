from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, cast

import asyncpg

from src.application.workbench.dto import WorkbenchProcessDocumentJobPayloadDto
from src.application.workbench_commands.manual_resume import (
    WorkbenchManualResumeCommand,
    WorkbenchManualResumeNotFoundError,
    WorkbenchManualResumeRejectedError,
    WorkbenchManualResumeService,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)
from src.infrastructure.queue.job_types import (
    TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING,
)
from src.domain.project_plane.knowledge_workbench.shared import JsonValue


class WorkbenchManualResumeDbPool(Protocol):
    async def acquire(self): ...


class WorkbenchManualResumeQueueRepository(Protocol):
    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, JsonValue] | None = None,
        max_attempts: int = 3,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class WorkbenchResumeParallelQueueAdapter:
    queue_repository: WorkbenchManualResumeQueueRepository

    async def enqueue_process_workbench_document(
        self,
        payload: WorkbenchProcessDocumentJobPayloadDto,
    ) -> None:
        await self.queue_repository.enqueue(
            task_type=TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING,
            payload={
                "project_id": payload.project_id,
                "document_id": payload.document_id,
                "processing_run_id": payload.processing_run_id,
                "section_worker_count": 3,
                "worker_id_prefix": "workbench-parallel",
                "lease_seconds": 300,
                "max_cycles": 10_000,
                "max_registry_drain_steps_per_cycle": 10_000,
            },
        )


async def resume_workbench_document(
    *,
    pool: WorkbenchManualResumeDbPool,
    queue_repo: WorkbenchManualResumeQueueRepository,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = _workbench_repository(connection)
        queue = WorkbenchResumeParallelQueueAdapter(queue_repository=queue_repo)
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


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return factory(connection)
