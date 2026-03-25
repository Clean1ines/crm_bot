"""
Queue Repository for background task management.

This module provides data access methods for the execution_queue table,
supporting reliable task processing with retry logic and worker tracking.
"""

import uuid
import json
import asyncpg
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from src.core.logging import get_logger
from src.core.config import settings

logger = get_logger(__name__)


class QueueRepository:
    """
    Repository for managing background job queue operations.
    
    Supports reliable task processing with atomic claim, retry logic,
    timeout handling, and worker tracking for horizontal scaling.
    
    Attributes:
        pool: Asyncpg connection pool for database operations.
    """
    
    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the QueueRepository with a database connection pool.
        
        Args:
            pool: Asyncpg connection pool for database operations.
        """
        self.pool = pool
        logger.debug("QueueRepository initialized")

    async def enqueue(
        self, 
        task_type: str, 
        payload: Optional[Dict[str, Any]] = None,
        max_attempts: int = 3
    ) -> str:
        """
        Добавляет задачу в очередь.
        Возвращает ID созданной задачи.
        
        Args:
            task_type: Тип задачи (например, 'notify_manager').
            payload: Данные задачи в виде словаря.
            max_attempts: Максимальное количество попыток выполнения.
        
        Returns:
            UUID новой задачи в строковом формате.
        """
        logger.info(
            "Enqueuing job",
            extra={"task_type": task_type, "payload_keys": list(payload.keys()) if payload else None}
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
            job_id = str(row['id'])
            logger.info("Job enqueued successfully", extra={"job_id": job_id})
            return job_id

    async def claim_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Захватывает одну задачу из очереди для обработки.
        Возвращает словарь с данными задачи или None, если задач нет.
        
        Использует `FOR UPDATE SKIP LOCKED` для защиты от гонок
        между воркерами и устанавливает `locked_at` для timeout detection.
        
        Args:
            worker_id: Уникальный идентификатор воркера.
        
        Returns:
            Dict с данными задачи или None если задач нет.
        """
        # Log connection info to debug schema issues
        async with self.pool.acquire() as conn:
            db_name = await conn.fetchval("SELECT current_database()")
            schema_name = await conn.fetchval("SELECT current_schema()")
            

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
                #logger.debug("No pending jobs available", extra={"worker_id": worker_id})
                return None
            
            job = dict(row)
            job['id'] = str(job['id'])
            if job['payload'] and isinstance(job['payload'], str):
                try:
                    job['payload'] = json.loads(job['payload'])
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Failed to parse job payload",
                        extra={"job_id": job['id'], "error": str(e)}
                    )
                    job['payload'] = {}
            
            logger.info(
                "Job claimed successfully",
                extra={"job_id": job['id'], "task_type": job['task_type'], "worker_id": worker_id}
            )
            return job

    async def complete_job(self, job_id: str, success: bool, error: Optional[str] = None) -> None:
        """
        Помечает задачу как выполненную (status = 'done') или неудавшуюся (status = 'failed').
        
        Args:
            job_id: UUID задачи в строковом формате.
            success: True если задача выполнена успешно, False если нет.
            error: Сообщение об ошибке при неудачном выполнении.
        """
        new_status = 'done' if success else 'failed'
        logger.info(
            "Completing job",
            extra={"job_id": job_id, "status": new_status, "error": error}
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
        """
        Освобождает заблокированную задачу для повторной обработки.
        
        Используется для recovery задач, которые зависли у воркера
        (например, при падении процесса или сетевой ошибке).
        
        Args:
            job_id: UUID задачи в строковом формате.
            reason: Причина освобождения (для логирования).
        
        Returns:
            True если задача была освобождена, False если не найдена.
        """
        logger.info(
            "Releasing job",
            extra={"job_id": job_id, "reason": reason}
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
                    extra={"job_id": job_id}
                )
            return released

    async def fail_job(self, job_id: str, error: str, increment_attempt: bool = True) -> bool:
        """
        Помечает задачу как неудавшуюся с увеличением счётчика попыток.
        
        Args:
            job_id: UUID задачи в строковом формате.
            error: Сообщение об ошибке.
            increment_attempt: Увеличивать ли счётчик попыток.
        
        Returns:
            True если задача обновлена, False если не найдена.
        """
        logger.info(
            "Failing job",
            extra={"job_id": job_id, "error": error, "increment_attempt": increment_attempt}
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
        """
        Увеличивает счётчик попыток для задачи и возвращает новое значение.
        
        Args:
            job_id: UUID задачи в строковом формате.
        
        Returns:
            Новое значение attempts или None если задача не найдена.
        """
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
            
            attempts = row['attempts']
            max_attempts = row['max_attempts']
            
            logger.debug(
                "Attempts incremented",
                extra={"job_id": job_id, "attempts": attempts, "max_attempts": max_attempts}
            )
            return attempts

    async def get_stale_locked_jobs(self, timeout_minutes: int = 5) -> list[str]:
        """
        Находит задачи, которые заблокированы дольше указанного таймаута.
        
        Используется для recovery зависших задач.
        
        Args:
            timeout_minutes: Таймаут в минутах.
        
        Returns:
            Список UUID заблокированных задач.
        """
        #logger.debug(
           # "Searching for stale locked jobs",
            #extra={"timeout_minutes": timeout_minutes}
        #)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id FROM public.execution_queue
                WHERE status = 'processing'
                AND locked_at < NOW() - INTERVAL '%s minutes'
            """ % timeout_minutes)
            
            job_ids = [str(row['id']) for row in rows]
            #logger.info(
               # "Found stale locked jobs",
               # extra={"count": len(job_ids), "timeout_minutes": timeout_minutes}
           # )
            return job_ids
