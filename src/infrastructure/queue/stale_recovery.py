"""Recovery for queue jobs locked by dead/stuck workers."""

from __future__ import annotations

from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


async def recover_stale_jobs(
    queue_repo: QueueRepository,
    *,
    timeout_minutes: int = 5,
) -> int:
    """
    Release jobs stuck in processing longer than timeout.

    Returns number of released jobs. Recovery failure is non-fatal for worker loop.
    """
    try:
        stale_jobs = await queue_repo.get_stale_locked_jobs(timeout_minutes)
        released = 0

        for job_id in stale_jobs:
            logger.warning(
                "Recovering stale job",
                extra={"job_id": job_id, "timeout_minutes": timeout_minutes},
            )
            if await queue_repo.release_job(job_id, reason="stale_lock_recovery"):
                released += 1

        return released
    except Exception as exc:
        logger.error("Failed to recover stale jobs", extra={"error": str(exc)})
        return 0
