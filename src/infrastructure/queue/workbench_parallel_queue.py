from __future__ import annotations

import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.infrastructure.queue.handlers.workbench_parallel_processing import (
    PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE,
    WorkbenchParallelProcessingJobPayloadDto,
)


class WorkbenchParallelQueueConnection(Protocol):
    def execute(self, query: str, *args: object) -> Awaitable[object]: ...


@dataclass(frozen=True, slots=True)
class EnqueueWorkbenchParallelProcessingCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    section_worker_count: int = 3
    worker_id_prefix: str = "workbench-parallel"
    lease_seconds: int = 300
    max_cycles: int = 10_000
    max_registry_drain_steps_per_cycle: int = 10_000

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("parallel enqueue requires project_id")
        if not self.document_id:
            raise DomainInvariantError("parallel enqueue requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError("parallel enqueue requires processing_run_id")
        if self.section_worker_count < 1:
            raise DomainInvariantError(
                "parallel enqueue section_worker_count must be positive"
            )
        if not self.worker_id_prefix:
            raise DomainInvariantError("parallel enqueue requires worker_id_prefix")
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "parallel enqueue lease_seconds must be positive"
            )
        if self.max_cycles < 1:
            raise DomainInvariantError("parallel enqueue max_cycles must be positive")
        if self.max_registry_drain_steps_per_cycle < 1:
            raise DomainInvariantError(
                "parallel enqueue registry drain limit must be positive"
            )

    def to_payload_dto(self) -> WorkbenchParallelProcessingJobPayloadDto:
        return WorkbenchParallelProcessingJobPayloadDto(
            project_id=self.project_id,
            document_id=self.document_id,
            processing_run_id=self.processing_run_id,
            section_worker_count=self.section_worker_count,
            worker_id_prefix=self.worker_id_prefix,
            lease_seconds=self.lease_seconds,
            max_cycles=self.max_cycles,
            max_registry_drain_steps_per_cycle=(
                self.max_registry_drain_steps_per_cycle
            ),
        )


@dataclass(frozen=True, slots=True)
class EnqueueWorkbenchParallelProcessingResult:
    task_type: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class WorkbenchParallelQueueAdapter:
    connection: WorkbenchParallelQueueConnection

    async def enqueue_process_workbench_document(
        self,
        command: object,
    ) -> EnqueueWorkbenchParallelProcessingResult:
        return await self.enqueue_process_workbench_parallel_processing(
            EnqueueWorkbenchParallelProcessingCommand(
                project_id=str(getattr(command, "project_id")),
                document_id=str(getattr(command, "document_id")),
                processing_run_id=str(getattr(command, "processing_run_id")),
                section_worker_count=3,
            )
        )

    async def enqueue_process_workbench_parallel_processing(
        self,
        command: EnqueueWorkbenchParallelProcessingCommand,
    ) -> EnqueueWorkbenchParallelProcessingResult:
        payload = _payload_mapping(command.to_payload_dto())

        await self.connection.execute(
            """
            INSERT INTO execution_queue (task_type, payload)
            VALUES ($1, $2::jsonb)
            """,
            PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )

        return EnqueueWorkbenchParallelProcessingResult(
            task_type=PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE,
            payload=payload,
        )


def _payload_mapping(
    payload: WorkbenchParallelProcessingJobPayloadDto,
) -> dict[str, object]:
    return {
        "project_id": payload.project_id,
        "document_id": payload.document_id,
        "processing_run_id": payload.processing_run_id,
        "section_worker_count": payload.section_worker_count,
        "worker_id_prefix": payload.worker_id_prefix,
        "lease_seconds": payload.lease_seconds,
        "max_cycles": payload.max_cycles,
        "max_registry_drain_steps_per_cycle": (
            payload.max_registry_drain_steps_per_cycle
        ),
    }


__all__ = [
    "EnqueueWorkbenchParallelProcessingCommand",
    "EnqueueWorkbenchParallelProcessingResult",
    "WorkbenchParallelQueueAdapter",
    "WorkbenchParallelQueueConnection",
]
