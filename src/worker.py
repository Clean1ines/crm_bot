"""
Worker process for handling background tasks from the execution queue.
Currently supports:
- notify_manager: sends an inline keyboard notification to the manager.
"""

import asyncio
import signal
import asyncpg
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid

from src.core.config import settings
from src.core.logging import get_logger
from src.database.repositories.queue_repository import QueueRepository
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.project_repository import ProjectRepository

logger = get_logger(__name__)

shutdown_event = asyncio.Event()

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 60


def handle_sigterm():
    """Signal handler for graceful shutdown."""
    logger.info("Received SIGTERM, shutting down...")
    shutdown_event.set()


def calculate_backoff(attempt: int) -> float:
    """
    Calculate exponential backoff delay with jitter.
    
    Args:
        attempt: Current attempt number (0-based).
    
    Returns:
        Delay in seconds with exponential backoff and jitter.
    """
    import random
    delay = min(INITIAL_BACKOFF_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS)
    # Add jitter to prevent thundering herd
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


async def worker_loop(pool: asyncpg.Pool) -> None:
    """
    Main worker loop: continuously claim jobs from the queue and process them.
    
    Implements retry logic with exponential backoff and timeout recovery
    for stale locked jobs.
    
    Args:
        pool: Asyncpg connection pool for database operations.
    """
    queue_repo = QueueRepository(pool)
    thread_repo = ThreadRepository(pool)
    project_repo = ProjectRepository(pool)
    
    worker_id = f"worker-{id(asyncio.current_task())}"
    logger.info("Worker started", extra={"worker_id": worker_id})

    while not shutdown_event.is_set():
        try:
            # Periodic recovery: release stale locked jobs
            await _recover_stale_jobs(queue_repo, timeout_minutes=5)
            
            job = await queue_repo.claim_job(worker_id)
            if not job:
                await asyncio.sleep(1)
                continue

            logger.info(
                "Processing job",
                extra={
                    "job_id": job['id'],
                    "task_type": job['task_type'],
                    "worker_id": worker_id,
                    "attempt": job.get('attempts', 0)
                }
            )

            if job["task_type"] == "notify_manager":
                success = await _handle_notify_manager(
                    job, thread_repo, project_repo, queue_repo, worker_id
                )
                
                if success:
                    await queue_repo.complete_job(job["id"], success=True)
                else:
                    # Use fail_job to handle retry logic
                    attempts = job.get('attempts', 0)
                    max_attempts = job.get('max_attempts', MAX_RETRIES)
                    
                    if attempts + 1 >= max_attempts:
                        await queue_repo.fail_job(
                            job["id"], 
                            error="Max attempts reached",
                            increment_attempt=False  # Already counted in claim
                        )
                        logger.warning(
                            "Job failed permanently",
                            extra={"job_id": job["id"], "attempts": attempts}
                        )
                    else:
                        await queue_repo.fail_job(
                            job["id"],
                            error="Transient failure, will retry",
                            increment_attempt=False
                        )
                        # Exponential backoff before next attempt
                        backoff = calculate_backoff(attempts)
                        logger.info(
                            "Job will be retried",
                            extra={"job_id": job["id"], "backoff_seconds": backoff, "next_attempt": attempts + 1}
                        )
                        await asyncio.sleep(backoff)

            else:
                logger.warning(
                    "Unknown task type",
                    extra={"job_id": job["id"], "task_type": job["task_type"]}
                )
                await queue_repo.complete_job(job["id"], success=False)

        except asyncio.CancelledError:
            logger.info("Worker loop cancelled", extra={"worker_id": worker_id})
            break
        except Exception as e:
            logger.exception("Error in worker loop", extra={"worker_id": worker_id})
            await asyncio.sleep(5)  # Prevent tight error loop

    logger.info("Worker shutting down", extra={"worker_id": worker_id})


async def _recover_stale_jobs(queue_repo: QueueRepository, timeout_minutes: int = 5) -> None:
    """
    Recover jobs that have been locked longer than the timeout.
    
    Args:
        queue_repo: QueueRepository instance.
        timeout_minutes: Timeout threshold in minutes.
    """
    try:
        stale_jobs = await queue_repo.get_stale_locked_jobs(timeout_minutes)
        for job_id in stale_jobs:
            logger.warning(
                "Recovering stale job",
                extra={"job_id": job_id, "timeout_minutes": timeout_minutes}
            )
            await queue_repo.release_job(job_id, reason="stale_lock_recovery")
    except Exception as e:
        logger.error("Failed to recover stale jobs", extra={"error": str(e)})


async def _handle_notify_manager(
    job: Dict[str, Any],
    thread_repo: ThreadRepository,
    project_repo: ProjectRepository,
    queue_repo: QueueRepository,
    worker_id: str
) -> bool:
    """
    Handle the notify_manager task type.
    
    Sends inline keyboard notifications to all managers for a project.
    
    Args:
        job: Job data from claim_job.
        thread_repo: ThreadRepository instance.
        project_repo: ProjectRepository instance.
        queue_repo: QueueRepository instance.
        worker_id: Current worker identifier.
    
    Returns:
        True if notification sent successfully to at least one manager.
    """
    payload = job.get("payload") or {}
    # Ensure thread_id is string
    thread_id = str(payload.get("thread_id"))
    chat_id = payload.get("chat_id")
    message = payload.get("message")

    # Get thread info to find project_id
    thread_info = await thread_repo.get_thread_with_project(thread_id)
    if not thread_info:
        logger.error("Thread not found", extra={"thread_id": thread_id, "job_id": job["id"]})
        return False
    
    project_id = thread_info["project_id"]

    # Get manager settings for this project
    project_settings = await project_repo.get_project_settings(str(project_id))
    manager_bot_token = project_settings.get("manager_bot_token")
    manager_chat_ids = project_settings.get("manager_chat_ids", [])

    if not manager_bot_token:
        logger.error(
            "Manager bot token not set",
            extra={"project_id": project_id, "job_id": job["id"]}
        )
        return False

    if not manager_chat_ids:
        logger.warning(
            "No managers defined for project",
            extra={"project_id": project_id, "job_id": job["id"]}
        )
        return False

    # Build inline keyboard markup with two buttons: reply and close
    reply_markup = {
        "inline_keyboard": [
            [{"text": "✏️ Ответить", "callback_data": f"reply:{thread_id}"}],
            [{"text": "✅ Закрыть тикет", "callback_data": f"close:{thread_id}"}]
        ]
    }

    # Send notification to all managers
    success_count = 0
    for mgr_chat_id in manager_chat_ids:
        url = f"https://api.telegram.org/bot{manager_bot_token}/sendMessage"
        params = {
            "chat_id": int(mgr_chat_id),
            "text": f"Новое сообщение (thread {thread_id}):\n\n{message}",
            "reply_markup": reply_markup
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=params)
                resp.raise_for_status()
            success_count += 1
            logger.info(
                "Manager notified",
                extra={
                    "job_id": job["id"],
                    "thread_id": thread_id,
                    "manager_chat_id": mgr_chat_id,
                    "worker_id": worker_id
                }
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error sending notification",
                extra={
                    "manager_chat_id": mgr_chat_id,
                    "status_code": e.response.status_code,
                    "job_id": job["id"]
                }
            )
        except httpx.RequestError as e:
            logger.error(
                "Request error sending notification",
                extra={
                    "manager_chat_id": mgr_chat_id,
                    "error": str(e),
                    "job_id": job["id"]
                }
            )
        except Exception as e:
            logger.error(
                "Unexpected error sending notification",
                extra={
                    "manager_chat_id": mgr_chat_id,
                    "error": str(e),
                    "job_id": job["id"]
                }
            )

    return success_count > 0


async def main():
    """
    Main entry point: set up signal handlers, create database pool, and run worker loop.
    """
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_sigterm)

    db_url = settings.DATABASE_URL
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    try:
        await worker_loop(pool)
    finally:
        await pool.close()
        logger.info("Database pool closed")


if __name__ == "__main__":
    asyncio.run(main())
