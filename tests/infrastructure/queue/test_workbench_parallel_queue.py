from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.infrastructure.queue.handlers.workbench_parallel_processing import (
    PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE,
)
from src.infrastructure.queue.workbench_parallel_queue import (
    EnqueueWorkbenchParallelProcessingCommand,
    WorkbenchParallelQueueAdapter,
)


@dataclass(slots=True)
class FakeQueueConnection:
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def execute(self, query: str, *args: object) -> object:
        self.calls.append((query, args))
        return "INSERT 0 1"


@pytest.mark.asyncio
async def test_parallel_queue_adapter_enqueues_parallel_task_payload() -> None:
    connection = FakeQueueConnection()
    adapter = WorkbenchParallelQueueAdapter(connection)

    result = await adapter.enqueue_process_workbench_parallel_processing(
        EnqueueWorkbenchParallelProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=3,
            worker_id_prefix="parallel-worker",
            lease_seconds=120,
            max_cycles=17,
            max_registry_drain_steps_per_cycle=19,
        )
    )

    assert result.task_type == PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE
    assert result.payload == {
        "project_id": "project-1",
        "document_id": "document-1",
        "processing_run_id": "processing-run-1",
        "section_worker_count": 3,
        "worker_id_prefix": "parallel-worker",
        "lease_seconds": 120,
        "max_cycles": 17,
        "max_registry_drain_steps_per_cycle": 19,
    }

    assert len(connection.calls) == 1
    query, args = connection.calls[0]
    assert "INSERT INTO execution_queue" in query
    assert "task_type" in query
    assert "payload" in query
    assert args[0] == "process_workbench_parallel_processing"
    assert json.loads(str(args[1])) == result.payload


@pytest.mark.asyncio
async def test_parallel_queue_adapter_defaults_to_three_section_workers() -> None:
    connection = FakeQueueConnection()
    adapter = WorkbenchParallelQueueAdapter(connection)

    result = await adapter.enqueue_process_workbench_parallel_processing(
        EnqueueWorkbenchParallelProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )
    )

    assert result.payload["section_worker_count"] == 3
    assert result.payload["worker_id_prefix"] == "workbench-parallel"
    assert result.payload["lease_seconds"] == 300
    assert result.payload["max_cycles"] == 10_000
    assert result.payload["max_registry_drain_steps_per_cycle"] == 10_000


def test_parallel_enqueue_command_rejects_missing_ids() -> None:
    with pytest.raises(DomainInvariantError, match="project_id"):
        EnqueueWorkbenchParallelProcessingCommand(
            project_id="",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )


def test_parallel_enqueue_command_rejects_non_positive_limits() -> None:
    with pytest.raises(DomainInvariantError, match="section_worker_count"):
        EnqueueWorkbenchParallelProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=0,
        )
