"""Queue worker runtime composition root."""

from __future__ import annotations

import asyncio
import signal
from dataclasses import asdict
from functools import partial
from typing import cast

import asyncpg
import redis.asyncio as redis

from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.manager_notifications import ManagerNotificationTarget
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.metrics_repository import MetricsRepository
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.thread.read import ThreadReadRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_dispatcher import JobDispatcher
from src.infrastructure.queue.handlers.notify_manager import RedisExistsPort
from src.infrastructure.queue.telegram_sender import TelegramSender
from src.infrastructure.queue.worker_loop import run_worker_loop
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)


class _RedisExistsAdapter(RedisExistsPort):
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def exists(self, key: str) -> object:
        return await self._client.exists(key)


async def _get_notify_manager_redis() -> RedisExistsPort:
    return _RedisExistsAdapter(await get_redis_client())


class ProjectNotificationAdapter:
    """Adapter from composed ProjectRepository views to queue notification port."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def get_project_settings(self, project_id: str) -> JsonObject | None:
        settings_view = await self._repo.get_project_settings(project_id)

        if hasattr(settings_view, "to_dict"):
            return cast(JsonObject, settings_view.to_dict())

        if hasattr(settings_view, "model_dump"):
            return cast(JsonObject, settings_view.model_dump())

        return cast(JsonObject, asdict(settings_view))

    async def get_manager_notification_recipients(
        self,
        project_id: str,
    ) -> list[ManagerNotificationTarget]:
        return await self._repo.get_manager_notification_recipients(project_id)


def request_shutdown(shutdown_event: asyncio.Event) -> None:
    logger.info("Received shutdown signal, shutting down...")
    shutdown_event.set()


async def worker_loop(pool: asyncpg.Pool) -> None:
    """
    Compatibility worker entrypoint.

    Existing code can still call src.infrastructure.queue.worker.worker_loop(pool).
    """
    shutdown_event = asyncio.Event()

    queue_repo = QueueRepository(pool)
    thread_read_repo = ThreadReadRepository(pool)
    project_repo = ProjectRepository(pool)
    metrics_repo = MetricsRepository(pool)

    dispatcher = JobDispatcher(
        thread_read_repo=thread_read_repo,
        db_pool=pool,
        project_repo=ProjectNotificationAdapter(project_repo),
        metrics_repo=metrics_repo,
        telegram_sender=TelegramSender(),
        redis_getter=_get_notify_manager_redis,
    )

    await run_worker_loop(
        queue_repo=queue_repo,
        dispatcher=dispatcher,
        shutdown_event=shutdown_event,
    )


async def main() -> None:
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, partial(request_shutdown, shutdown_event))

    db_url = settings.DATABASE_URL
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    try:
        queue_repo = QueueRepository(pool)
        thread_read_repo = ThreadReadRepository(pool)
        project_repo = ProjectRepository(pool)
        metrics_repo = MetricsRepository(pool)

        dispatcher = JobDispatcher(
            thread_read_repo=thread_read_repo,
            db_pool=pool,
            project_repo=ProjectNotificationAdapter(project_repo),
            metrics_repo=metrics_repo,
            telegram_sender=TelegramSender(),
            redis_getter=_get_notify_manager_redis,
        )

        await run_worker_loop(
            queue_repo=queue_repo,
            dispatcher=dispatcher,
            shutdown_event=shutdown_event,
        )
    finally:
        await pool.close()
        logger.info("Database pool closed")
