from __future__ import annotations

from dataclasses import dataclass, field

from src.application.workbench.dto import WorkbenchProcessDocumentJobPayloadDto
from src.infrastructure.queue.job_types import (
    KNOWN_TASK_TYPES,
    TASK_PROCESS_WORKBENCH_DOCUMENT,
)
from src.infrastructure.queue.workbench_queue import WorkbenchQueueAdapter


@dataclass(slots=True)
class EnqueuedJob:
    task_type: str
    payload: dict[str, object] | None
    max_attempts: int


@dataclass(slots=True)
class FakeQueueRepository:
    jobs: list[EnqueuedJob] = field(default_factory=list)

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, object] | None = None,
        max_attempts: int = 3,
    ) -> str:
        self.jobs.append(
            EnqueuedJob(
                task_type=task_type,
                payload=payload,
                max_attempts=max_attempts,
            )
        )
        return "job-1"


def test_workbench_task_type_is_known() -> None:
    assert TASK_PROCESS_WORKBENCH_DOCUMENT in KNOWN_TASK_TYPES


async def test_workbench_queue_adapter_enqueues_process_document_job() -> None:
    queue = FakeQueueRepository()
    adapter = WorkbenchQueueAdapter(queue_repository=queue, max_attempts=7)

    await adapter.enqueue_process_workbench_document(
        WorkbenchProcessDocumentJobPayloadDto.fresh_upload(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )
    )

    assert queue.jobs == [
        EnqueuedJob(
            task_type="process_workbench_document",
            payload={
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_run_id": "processing-run-1",
                "processing_method": "faq_section_registry_v1",
                "trigger": "fresh_upload",
                "source": "workbench_fresh_upload",
            },
            max_attempts=7,
        )
    ]
