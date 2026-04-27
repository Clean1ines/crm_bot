"""
Queue Repository for background task management.

This module provides data access methods for the execution_queue table,
supporting reliable task processing with retry logic and worker tracking.
"""

import json
from typing import Optional

import asyncpg

from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.queue_views import QueueJobView
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class QueueRepository:
    """
    Repository for managing background job queue operations.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        logger.debug("QueueRepository initialized")

    async def enqueue(
        self,
        task_type: str,
        payload: JsonObject | None = None,
        max_attempts: int = 3,
    ) -> str:
        logger.info(
            "Enqueuing job",
            extra={"task_type": task_type, "payload_keys": list(payload.keys()) if payload else None},
        )
        async with self.pool.acquire() as conn:
            payload_json = json.dumps(payload) if payload else None
            row = await conn.fetchrow("""
                INSERT INTO public.execution_queue (
                    id, task_type, payload, status, 
                    attempts, max_attempts, created_at, updated_at
                )
                VALUES (gen_random_uuid(), $1, $2, 'pending', 0, $3, NOW(), NOW())
                RETURNING id
            """, task_type, payload_json, max_attempts)
            job_id = str(row["id"])
            logger.info("Job enqueued successfully", extra={"job_id": job_id})
            return job_id

    async def claim_job(self, worker_id: str) -> QueueJobView | None:
        async with self.pool.acquire() as conn:
            await conn.fetchval("SELECT current_database()")
            await conn.fetchval("SELECT current_schema()")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE public.execution_queue
                SET 
                    status = 'processing',
                    updated_at = NOW(),
                    locked_at = NOW(),
                    worker_id = $1
                WHERE id = (
                    SELECT id
                    FROM public.execution_queue
                    WHERE status = 'pending'
                    AND (attempts < max_attempts OR max_attempts IS NULL)
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, task_type, payload, attempts, max_attempts, created_at
            """, worker_id)

            if not row:
                return None

            job_record = dict(row)
            job_record["id"] = str(job_record["id"])

            if job_record["payload"] and isinstance(job_record["payload"], str):
                try:
                    job_record["payload"] = json.loads(job_record["payload"])
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Failed to parse job payload",
                        extra={"job_id": job_record["id"], "error": str(exc)},
                    )
                    job_record["payload"] = {}

            job = QueueJobView.from_record(job_record)

            logger.info(
                "Job claimed successfully",
                extra={"job_id": job.id, "task_type": job.task_type, "worker_id": worker_id},
            )
            return job

    async def complete_job(self, job_id: str, success: bool, error: Optional[str] = None) -> None:
        new_status = "done" if success else "failed"
        logger.info(
            "Completing job",
            extra={"job_id": job_id, "status": new_status, "error": error},
        )
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE public.execution_queue
                SET 
                    status = $1, 
                    updated_at = NOW(),
                    locked_at = NULL,
                    worker_id = NULL,
                    error = $2
                WHERE id = $3
            """, new_status, error, job_id)

    async def release_job(self, job_id: str, reason: str = "timeout") -> bool:
        logger.info(
            "Releasing job",
            extra={"job_id": job_id, "reason": reason},
        )
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE public.execution_queue
                SET 
                    status = 'pending',
                    updated_at = NOW(),
                    locked_at = NULL,
                    worker_id = NULL
                WHERE id = $1 AND status = 'processing'
            """, job_id)

            released = result == "UPDATE 1"
            if released:
                logger.info("Job released successfully", extra={"job_id": job_id})
            else:
                logger.warning(
                    "Job release failed - not found or not processing",
                    extra={"job_id": job_id},
                )
            return released

    async def fail_job(self, job_id: str, error: str, increment_attempt: bool = True) -> bool:
        logger.info(
            "Failing job",
            extra={"job_id": job_id, "error": error, "increment_attempt": increment_attempt},
        )
        async with self.pool.acquire() as conn:
            if increment_attempt:
                result = await conn.execute("""
                    UPDATE public.execution_queue
                    SET 
                        attempts = attempts + 1,
                        error = $1,
                        updated_at = NOW(),
                        locked_at = NULL,
                        worker_id = NULL,
                        status = CASE 
                            WHEN attempts + 1 >= max_attempts THEN 'failed'
                            ELSE 'pending'
                        END
                    WHERE id = $2
                """, error, job_id)
            else:
                result = await conn.execute("""
                    UPDATE public.execution_queue
                    SET 
                        error = $1,
                        updated_at = NOW(),
                        locked_at = NULL,
                        worker_id = NULL,
                        status = 'failed'
                    WHERE id = $2
                """, error, job_id)

            updated = result == "UPDATE 1"
            if updated:
                logger.info("Job failed successfully", extra={"job_id": job_id})
            else:
                logger.warning("Job fail failed - not found", extra={"job_id": job_id})
            return updated

    async def increment_attempts(self, job_id: str) -> Optional[int]:
        logger.debug("Incrementing attempts", extra={"job_id": job_id})
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE public.execution_queue
                SET attempts = attempts + 1, updated_at = NOW()
                WHERE id = $1
                RETURNING attempts, max_attempts
            """, job_id)

            if not row:
                logger.warning("Job not found for attempt increment", extra={"job_id": job_id})
                return None

            attempts = row["attempts"]
            max_attempts = row["max_attempts"]

            logger.debug(
                "Attempts incremented",
                extra={"job_id": job_id, "attempts": attempts, "max_attempts": max_attempts},
            )
            return attempts

    async def get_stale_locked_jobs(self, timeout_minutes: int = 5) -> list[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id FROM public.execution_queue
                WHERE status = 'processing'
                AND locked_at < NOW() - INTERVAL '%s minutes'
            """ % timeout_minutes)

            return [str(row["id"]) for row in rows]
