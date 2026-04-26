"""Dispatch execution_queue jobs to dedicated handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from src.infrastructure.db.repositories.metrics_repository import MetricsRepository
from src.infrastructure.db.repositories.project import ProjectRepository
from src.application.ports.thread_port import ThreadReadPort
from src.infrastructure.queue.handlers.metrics import handle_aggregate_metrics, handle_update_metrics
from src.infrastructure.queue.handlers.notify_manager import handle_notify_manager
from src.infrastructure.queue.job_exceptions import PermanentJobError
from src.infrastructure.queue.job_types import (
    TASK_AGGREGATE_METRICS,
    TASK_NOTIFY_MANAGER,
    TASK_UPDATE_METRICS,
)
from src.infrastructure.queue.telegram_sender import TelegramSender

RedisGetter = Callable[[], Awaitable[Any]]


@dataclass(slots=True)
class JobDispatcher:
    thread_read_repo: ThreadReadPort
    db_pool: Any
    project_repo: ProjectRepository
    metrics_repo: MetricsRepository
    telegram_sender: TelegramSender
    redis_getter: RedisGetter

    async def dispatch(self, job: Mapping[str, object], *, worker_id: str) -> None:
        task_type = str(job.get("task_type") or "")

        if task_type == TASK_NOTIFY_MANAGER:
            await handle_notify_manager(
                job,
                thread_read_repo=self.thread_read_repo,
                db_pool=self.db_pool,
                project_repo=self.project_repo,
                telegram_sender=self.telegram_sender,
                redis_getter=self.redis_getter,
                worker_id=worker_id,
            )
            return

        if task_type == TASK_UPDATE_METRICS:
            await handle_update_metrics(
                job,
                metrics_repo=self.metrics_repo,
                thread_read_repo=self.thread_read_repo,
            )
            return

        if task_type == TASK_AGGREGATE_METRICS:
            await handle_aggregate_metrics(
                job,
                metrics_repo=self.metrics_repo,
            )
            return

        raise PermanentJobError(f"Unknown task type: {task_type}")
