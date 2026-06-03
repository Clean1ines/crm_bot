from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.workbench.dto import WorkbenchProcessDocumentJobPayloadDto
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown
from src.infrastructure.queue.job_types import TASK_PROCESS_WORKBENCH_DOCUMENT


class QueueRepositoryPort(Protocol):
    async def enqueue(
        self,
        task_type: str,
        payload: JsonObject | None = None,
        max_attempts: int = 3,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class WorkbenchQueueAdapter:
    queue_repository: QueueRepositoryPort
    max_attempts: int = 3

    async def enqueue_process_workbench_document(
        self,
        payload: WorkbenchProcessDocumentJobPayloadDto,
    ) -> None:
        await self.queue_repository.enqueue(
            TASK_PROCESS_WORKBENCH_DOCUMENT,
            payload=json_object_from_unknown(payload.to_queue_payload()),
            max_attempts=self.max_attempts,
        )
