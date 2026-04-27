"""Main queue worker loop."""

from __future__ import annotations

import asyncio
import uuid

from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_dispatcher import JobDispatcher
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError
from src.infrastructure.queue.retry_policy import build_retry_decision
from src.infrastructure.queue.stale_recovery import recover_stale_jobs

logger = get_logger(__name__)


async def run_worker_loop(
    *,
    queue_repo: QueueRepository,
    dispatcher: JobDispatcher,
    shutdown_event: asyncio.Event,
    worker_id: str | None = None,
    idle_sleep_seconds: float = 1.0,
    error_sleep_seconds: float = 5.0,
    stale_timeout_minutes: int = 5,
) -> None:
    """Continuously claim and process queue jobs."""
    resolved_worker_id = worker_id or f"worker-{uuid.uuid4()}"
    logger.info("Worker started", extra={"worker_id": resolved_worker_id})

    while not shutdown_event.is_set():
        try:
            await recover_stale_jobs(queue_repo, timeout_minutes=stale_timeout_minutes)

            job = await queue_repo.claim_job(resolved_worker_id)
            if not job:
                await asyncio.sleep(idle_sleep_seconds)
                continue

            job_id = job.id
            task_type = job.task_type
            job_record = job.to_record()

            logger.info(
                "Processing job",
                extra={
                    "job_id": job_id,
                    "task_type": task_type,
                    "worker_id": resolved_worker_id,
                    "attempt": job.attempts,
                },
            )

            try:
                await dispatcher.dispatch(job_record, worker_id=resolved_worker_id)
            except PermanentJobError as exc:
                logger.warning(
                    "Job failed permanently",
                    extra={"job_id": job_id, "task_type": task_type, "error": str(exc)},
                )
                await queue_repo.complete_job(job_id, success=False, error=str(exc))
            except TransientJobError as exc:
                decision = build_retry_decision(job_record, str(exc))
                await queue_repo.fail_job(job_id, error=decision.error, increment_attempt=True)

                if decision.should_retry:
                    logger.info(
                        "Job will be retried",
                        extra={
                            "job_id": job_id,
                            "task_type": task_type,
                            "backoff_seconds": decision.backoff_seconds,
                        },
                    )
                    await asyncio.sleep(decision.backoff_seconds)
                else:
                    logger.warning(
                        "Job retry attempts exhausted",
                        extra={"job_id": job_id, "task_type": task_type},
                    )
            else:
                await queue_repo.complete_job(job_id, success=True)

        except asyncio.CancelledError:
            logger.info("Worker loop cancelled", extra={"worker_id": resolved_worker_id})
            break
        except Exception:
            logger.exception("Error in worker loop", extra={"worker_id": resolved_worker_id})
            await asyncio.sleep(error_sleep_seconds)

    logger.info("Worker shutting down", extra={"worker_id": resolved_worker_id})
