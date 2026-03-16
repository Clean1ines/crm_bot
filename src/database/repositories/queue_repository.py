import uuid
import json
from typing import Optional, Dict, Any
from datetime import datetime
from src.core.logging import get_logger

logger = get_logger(__name__)

class QueueRepository:
    def __init__(self, pool):
        """
        Принимает пул соединений asyncpg.
        """
        self.pool = pool

    async def enqueue(self, task_type: str, payload: Optional[Dict[str, Any]] = None) -> str:
        """
        Добавляет задачу в очередь.
        Возвращает ID созданной задачи.
        """
        logger.info(f"Enqueuing job of type {task_type}", extra={"payload": payload})
        async with self.pool.acquire() as conn:
            payload_json = json.dumps(payload) if payload else None
            row = await conn.fetchrow("""
                INSERT INTO execution_queue (id, task_type, payload, status, created_at, updated_at)
                VALUES (gen_random_uuid(), $1, $2, 'pending', NOW(), NOW())
                RETURNING id
            """, task_type, payload_json)
            job_id = str(row['id'])
            logger.info(f"Job {job_id} enqueued successfully")
            return job_id

    async def claim_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Захватывает одну задачу из очереди для обработки.
        Возвращает словарь с данными задачи или None, если задач нет.
        """
        #logger.debug(f"Worker {worker_id} attempting to claim a job")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE execution_queue
                SET status = 'processing', updated_at = NOW()
                WHERE id = (
                    SELECT id
                    FROM execution_queue
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, task_type, payload, created_at
            """)
            if not row:
                #logger.debug("No pending jobs available")
                return None
            job = dict(row)
            # job['id'] уже является объектом asyncpg.pgproto.pgproto.UUID
            # преобразуем в строку для единообразия
            job['id'] = str(job['id'])
            if job['payload'] and isinstance(job['payload'], str):
                try:
                    job['payload'] = json.loads(job['payload'])
                except json.JSONDecodeError:
                    pass
            logger.info(f"Job {job['id']} claimed by worker {worker_id}")
            return job

    async def complete_job(self, job_id: str, success: bool) -> None:
        """
        Помечает задачу как выполненную (status = 'done') или неудавшуюся (status = 'failed').
        job_id может быть строкой или объектом UUID (из asyncpg).
        """
        new_status = 'done' if success else 'failed'
        logger.info(f"Completing job {job_id} with status {new_status}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE execution_queue
                SET status = $1, updated_at = NOW()
                WHERE id = $2
            """, new_status, job_id)  # передаём job_id как есть, asyncpg сам преобразует в UUID
