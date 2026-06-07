"""Main queue worker loop."""

from __future__ import annotations

import asyncio
import uuid

from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_dispatcher import JobDispatcher
from src.infrastructure.queue.job_types import (
    TASK_PROCESS_WORKBENCH_DOCUMENT,
    TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError
from src.infrastructure.queue.handlers.workbench_document import (
    mark_process_workbench_document_exhausted,
)
from src.infrastructure.queue.retry_policy import build_retry_decision
from src.infrastructure.queue.stale_recovery import recover_stale_jobs
from src.infrastructure.llm.groq_keyring import configured_groq_api_keys

logger = get_logger(__name__)


def _is_attempt_preserving_workbench_transient_retry(
    *,
    task_type: str,
    error: str,
) -> bool:
    return task_type == TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING and error.startswith(
        "retryable Prompt A "
    )


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
    groq_keys = configured_groq_api_keys()
    logger.info(
        "Worker started",
        extra={
            "worker_id": resolved_worker_id,
            "groq_key_count": len(groq_keys),
            "groq_key_slots": {
                "GROQ_API_KEY": bool(groq_keys[0:1]),
                "GROQ_API_KEY2_OR_LATER": len(groq_keys) >= 2,
                "GROQ_API_KEY3_OR_LATER": len(groq_keys) >= 3,
            },
        },
    )

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
                try:
                    await dispatcher.dispatch(job_record, worker_id=resolved_worker_id)
                except PermanentJobError as exc:
                    logger.warning(
                        "Job failed permanently",
                        extra={
                            "job_id": job_id,
                            "task_type": task_type,
                            "error": str(exc),
                        },
                    )
                    await queue_repo.complete_job(job_id, success=False, error=str(exc))
                except TransientJobError as exc:
                    error_message = str(exc)
                    decision = build_retry_decision(
                        job_record,
                        error_message,
                        retry_after_seconds=exc.retry_after_seconds,
                    )
                    if _is_attempt_preserving_workbench_transient_retry(
                        task_type=task_type,
                        error=error_message,
                    ):
                        await queue_repo.retry_job_without_attempt_increment(
                            job_id,
                            retry_delay_seconds=decision.backoff_seconds,
                            error=error_message,
                        )
                    else:
                        await queue_repo.fail_job(
                            job_id,
                            increment_attempt=True,
                            retry_delay_seconds=decision.backoff_seconds,
                            error=error_message,
                        )
                        if (
                            decision.exhausted
                            and task_type == TASK_PROCESS_WORKBENCH_DOCUMENT
                        ):
                            await mark_process_workbench_document_exhausted(
                                job_record,
                            )
                else:
                    await queue_repo.complete_job(job_id, success=True)
                    logger.info(
                        "Job completed successfully",
                        extra={"job_id": job_id, "task_type": task_type},
                    )
            except Exception as exc:
                logger.exception(
                    "Unexpected job dispatch error",
                    extra={
                        "job_id": job_id,
                        "task_type": task_type,
                        "worker_id": resolved_worker_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:240],
                    },
                )
                decision = build_retry_decision(
                    job_record,
                    f"unexpected_dispatch_error:{type(exc).__name__}:{exc}",
                    retry_after_seconds=1.0,
                )
                await queue_repo.fail_job(
                    job_id,
                    increment_attempt=True,
                    retry_delay_seconds=decision.backoff_seconds,
                    error=str(exc),
                )
        except Exception as exc:
            logger.error(
                "Unexpected worker loop error",
                extra={
                    "worker_id": resolved_worker_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                },
            )
            await asyncio.sleep(error_sleep_seconds)

    logger.info("Worker shutting down", extra={"worker_id": resolved_worker_id})
