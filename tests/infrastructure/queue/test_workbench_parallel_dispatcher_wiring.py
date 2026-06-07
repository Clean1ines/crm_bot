from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping

import pytest

from src.infrastructure.queue import job_dispatcher as dispatcher_module
from src.infrastructure.queue.job_dispatcher import JobDispatcher
from src.infrastructure.queue.job_types import (
    TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING,
)


@dataclass(slots=True)
class CapturedParallelHandler:
    calls: list[dict[str, object]] = field(default_factory=list)

    async def __call__(
        self,
        *,
        payload: Mapping[str, object],
        connection: object,
    ) -> None:
        self.calls.append({"payload": dict(payload), "connection": connection})


class DummyTelegramSender:
    pass


@pytest.mark.asyncio
async def test_dispatcher_routes_parallel_workbench_task_from_json_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = CapturedParallelHandler()
    monkeypatch.setattr(
        dispatcher_module,
        "handle_workbench_parallel_processing_job_from_connection",
        captured,
    )

    db_pool = object()
    dispatcher = JobDispatcher(
        thread_read_repo=object(),
        db_pool=db_pool,
        project_repo=object(),
        metrics_repo=object(),
        telegram_sender=DummyTelegramSender(),
        redis_getter=object(),
    )

    await dispatcher.dispatch(
        {
            "task_type": TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING,
            "payload": json.dumps(
                {
                    "project_id": "project-1",
                    "document_id": "document-1",
                    "processing_run_id": "processing-run-1",
                    "section_worker_count": 4,
                }
            ),
        },
        worker_id="worker-1",
    )

    assert len(captured.calls) == 1
    assert captured.calls[0]["connection"] is db_pool
    assert captured.calls[0]["payload"] == {
        "project_id": "project-1",
        "document_id": "document-1",
        "processing_run_id": "processing-run-1",
        "section_worker_count": 4,
    }


@pytest.mark.asyncio
async def test_dispatcher_routes_parallel_workbench_task_from_mapping_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = CapturedParallelHandler()
    monkeypatch.setattr(
        dispatcher_module,
        "handle_workbench_parallel_processing_job_from_connection",
        captured,
    )

    dispatcher = JobDispatcher(
        thread_read_repo=object(),
        db_pool=object(),
        project_repo=object(),
        metrics_repo=object(),
        telegram_sender=DummyTelegramSender(),
        redis_getter=object(),
    )

    await dispatcher.dispatch(
        {
            "task_type": TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING,
            "payload": {
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_run_id": "processing-run-1",
            },
        },
        worker_id="worker-1",
    )

    assert len(captured.calls) == 1
    assert captured.calls[0]["payload"]["project_id"] == "project-1"
