"""Dispatch execution_queue jobs to dedicated handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.infrastructure.db.repositories.metrics_repository import MetricsRepository
from src.application.ports.project_port import ProjectNotificationPort
from src.application.ports.thread_port import ThreadReadPort
from src.infrastructure.queue.handlers.metrics import (
    handle_aggregate_metrics,
    handle_update_metrics,
)
from src.infrastructure.queue.handlers.knowledge_upload import (
    handle_process_knowledge_upload,
)
from src.infrastructure.queue.handlers.rag_eval import handle_run_full_rag_eval
from src.infrastructure.queue.handlers.notify_manager import (
    RedisGetter,
    handle_notify_manager,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError
from src.infrastructure.queue.job_types import (
    TASK_AGGREGATE_METRICS,
    TASK_NOTIFY_MANAGER,
    TASK_PROCESS_KNOWLEDGE_UPLOAD,
    TASK_RUN_FULL_RAG_EVAL,
    TASK_UPDATE_METRICS,
)
from src.infrastructure.queue.telegram_sender import TelegramSender


@dataclass(slots=True)
class JobDispatcher:
    thread_read_repo: ThreadReadPort
    db_pool: object
    project_repo: ProjectNotificationPort
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

        if task_type == TASK_PROCESS_KNOWLEDGE_UPLOAD:
            await handle_process_knowledge_upload(
                job,
                db_pool=self.db_pool,
            )
            return

        if task_type == TASK_RUN_FULL_RAG_EVAL:
            await handle_run_full_rag_eval(
                job,
                db_pool=self.db_pool,
            )
            return

        raise PermanentJobError(f"Unknown task type: {task_type}")
