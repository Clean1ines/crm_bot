from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from src.domain.project_plane.queue_views import QueueJobView
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError
from src.infrastructure.queue.worker_loop import run_worker_loop


@dataclass(slots=True)
class FakeQueueRepository:
    jobs: list[QueueJobView]
    claimed: list[str] = field(default_factory=list)
    completed: list[tuple[str, bool, str | None]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    stale_recoveries: int = 0

    async def claim_job(self, worker_id: str) -> QueueJobView | None:
        self.claimed.append(worker_id)
        if self.jobs:
            return self.jobs.pop(0)
        return None

    async def complete_job(
        self,
        job_id: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        self.completed.append((job_id, success, error))

    async def fail_job(
        self,
        job_id: str,
        error: str,
        increment_attempt: bool = True,
        retry_delay_seconds: float | None = None,
    ) -> bool:
        self.failed.append(
            {
                "job_id": job_id,
                "error": error,
                "increment_attempt": increment_attempt,
                "retry_delay_seconds": retry_delay_seconds,
            }
        )
        return True

    async def get_stale_locked_jobs(self, timeout_minutes: int = 5) -> list[str]:
        self.stale_recoveries += 1
        return []

    async def release_job(self, job_id: str, reason: str = "timeout") -> bool:
        return True


@dataclass(slots=True)
class FakeDispatcher:
    outcomes: list[object]
    calls: list[dict[str, Any]] = field(default_factory=list)
    db_pool: object = object()

    async def dispatch(self, job: dict[str, Any], *, worker_id: str) -> None:
        self.calls.append({"job": job, "worker_id": worker_id})
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome


def _job(job_id: str, *, attempts: int = 0, max_attempts: int = 3) -> QueueJobView:
    return QueueJobView.from_record(
        {
            "id": job_id,
            "task_type": "example_task",
            "payload": {"x": 1},
            "attempts": attempts,
            "max_attempts": max_attempts,
            "created_at": None,
        }
    )


async def _stop_soon(event: asyncio.Event) -> None:
    await asyncio.sleep(0)
    event.set()


@pytest.mark.asyncio
async def test_worker_loop_completes_job_successfully_after_dispatch_returns() -> None:
    shutdown_event = asyncio.Event()
    queue_repo = FakeQueueRepository(jobs=[_job("job-1")])
    dispatcher = FakeDispatcher(outcomes=[None])

    await asyncio.gather(
        run_worker_loop(
            queue_repo=queue_repo,  # type: ignore[arg-type]
            dispatcher=dispatcher,  # type: ignore[arg-type]
            shutdown_event=shutdown_event,
            worker_id="worker-1",
            idle_sleep_seconds=0.001,
            error_sleep_seconds=0.001,
        ),
        _stop_soon(shutdown_event),
    )

    assert dispatcher.calls
    assert queue_repo.completed == [("job-1", True, None)]
    assert queue_repo.failed == []


@pytest.mark.asyncio
async def test_worker_loop_marks_permanent_job_error_as_failed_without_retry() -> None:
    shutdown_event = asyncio.Event()
    queue_repo = FakeQueueRepository(jobs=[_job("job-1")])
    dispatcher = FakeDispatcher(outcomes=[PermanentJobError("bad payload")])

    await asyncio.gather(
        run_worker_loop(
            queue_repo=queue_repo,  # type: ignore[arg-type]
            dispatcher=dispatcher,  # type: ignore[arg-type]
            shutdown_event=shutdown_event,
            worker_id="worker-1",
            idle_sleep_seconds=0.001,
            error_sleep_seconds=0.001,
        ),
        _stop_soon(shutdown_event),
    )

    assert queue_repo.completed == [("job-1", False, "bad payload")]
    assert queue_repo.failed == []


@pytest.mark.asyncio
async def test_worker_loop_retries_transient_job_error() -> None:
    shutdown_event = asyncio.Event()
    queue_repo = FakeQueueRepository(jobs=[_job("job-1")])
    dispatcher = FakeDispatcher(
        outcomes=[TransientJobError("temporary", retry_after_seconds=7)]
    )

    await asyncio.gather(
        run_worker_loop(
            queue_repo=queue_repo,  # type: ignore[arg-type]
            dispatcher=dispatcher,  # type: ignore[arg-type]
            shutdown_event=shutdown_event,
            worker_id="worker-1",
            idle_sleep_seconds=0.001,
            error_sleep_seconds=0.001,
        ),
        _stop_soon(shutdown_event),
    )

    assert queue_repo.completed == []
    assert len(queue_repo.failed) == 1
    assert queue_repo.failed[0]["job_id"] == "job-1"
    assert queue_repo.failed[0]["increment_attempt"] is True
    assert queue_repo.failed[0]["retry_delay_seconds"] is not None


@pytest.mark.asyncio
async def test_worker_loop_continues_after_one_successful_job_until_shutdown() -> None:
    shutdown_event = asyncio.Event()
    queue_repo = FakeQueueRepository(jobs=[_job("job-1"), _job("job-2")])
    dispatcher = FakeDispatcher(outcomes=[None, None])

    async def stop_after_two_dispatches() -> None:
        for _ in range(100):
            if len(dispatcher.calls) >= 2:
                shutdown_event.set()
                return
            await asyncio.sleep(0.001)
        shutdown_event.set()

    await asyncio.gather(
        run_worker_loop(
            queue_repo=queue_repo,  # type: ignore[arg-type]
            dispatcher=dispatcher,  # type: ignore[arg-type]
            shutdown_event=shutdown_event,
            worker_id="worker-1",
            idle_sleep_seconds=0.001,
            error_sleep_seconds=0.001,
        ),
        stop_after_two_dispatches(),
    )

    assert [call[0] for call in queue_repo.completed] == ["job-1", "job-2"]
    assert len(dispatcher.calls) == 2
