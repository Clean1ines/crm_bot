"""Queue worker runtime composition root."""

from __future__ import annotations

import asyncio
import signal

import asyncpg

from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.metrics_repository import MetricsRepository
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.thread_repository import ThreadRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_dispatcher import JobDispatcher
from src.infrastructure.queue.telegram_sender import TelegramSender
from src.infrastructure.queue.worker_loop import run_worker_loop
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)


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
    thread_repo = ThreadRepository(pool)
    project_repo = ProjectRepository(pool)
    metrics_repo = MetricsRepository(pool)

    dispatcher = JobDispatcher(
        thread_repo=thread_repo,
        project_repo=project_repo,
        metrics_repo=metrics_repo,
        telegram_sender=TelegramSender(),
        redis_getter=get_redis_client,
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
        loop.add_signal_handler(sig, lambda event=shutdown_event: request_shutdown(event))

    db_url = settings.DATABASE_URL
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    try:
        queue_repo = QueueRepository(pool)
        thread_repo = ThreadRepository(pool)
        project_repo = ProjectRepository(pool)
        metrics_repo = MetricsRepository(pool)

        dispatcher = JobDispatcher(
            thread_repo=thread_repo,
            project_repo=project_repo,
            metrics_repo=metrics_repo,
            telegram_sender=TelegramSender(),
            redis_getter=get_redis_client,
        )

        await run_worker_loop(
            queue_repo=queue_repo,
            dispatcher=dispatcher,
            shutdown_event=shutdown_event,
        )
    finally:
        await pool.close()
        logger.info("Database pool closed")
