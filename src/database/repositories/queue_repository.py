import uuid
import json
from typing import Optional, Dict, Any
from datetime import datetime

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
        async with self.pool.acquire() as conn:
            # Преобразуем payload в JSON-строку, если он есть
            payload_json = json.dumps(payload) if payload else None
            row = await conn.fetchrow("""
                INSERT INTO execution_queue (id, task_type, payload, status, created_at, updated_at)
                VALUES (gen_random_uuid(), $1, $2, 'pending', NOW(), NOW())
                RETURNING id
            """, task_type, payload_json)
            return str(row['id'])

    async def claim_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Захватывает одну задачу из очереди для обработки.
        Возвращает словарь с данными задачи или None, если задач нет.
        """
        async with self.pool.acquire() as conn:
            # Выбираем самую старую pending-задачу и блокируем её
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
                return None
            # Преобразуем результат
            job = dict(row)
            # Если payload строка, пытаемся распарсить JSON
            if job['payload'] and isinstance(job['payload'], str):
                try:
                    job['payload'] = json.loads(job['payload'])
                except json.JSONDecodeError:
                    # оставляем как есть, если не JSON
                    pass
            return job

    async def complete_job(self, job_id: str, success: bool) -> None:
        """
        Помечает задачу как выполненную (status = 'done') или неудавшуюся (status = 'failed').
        """
        new_status = 'done' if success else 'failed'
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE execution_queue
                SET status = $1, updated_at = NOW()
                WHERE id = $2
            """, new_status, uuid.UUID(job_id))
