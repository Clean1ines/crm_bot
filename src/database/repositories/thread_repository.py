import uuid
from typing import List, Optional, Dict
from ..models import ThreadStatus
from src.core.logging import get_logger

logger = get_logger(__name__)

class ThreadRepository:
    def __init__(self, pool):
        """
        Принимает пул соединений asyncpg.
        """
        self.pool = pool

    async def get_or_create_client(self, project_id: str, chat_id: int, username: str = None) -> str:
        """Возвращает UUID клиента, создавая его при необходимости."""
        logger.info(f"Getting or creating client for project {project_id}, chat {chat_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO clients (project_id, chat_id, username)
                VALUES ($1, $2, $3)
                ON CONFLICT (project_id, chat_id) DO UPDATE SET username = EXCLUDED.username
                RETURNING id
            """, uuid.UUID(project_id), chat_id, username)
            client_id = str(row['id'])
            logger.info(f"Client {client_id} ensured")
            return client_id

    async def get_active_thread(self, client_id: str) -> Optional[str]:
        """Ищет последний активный тред клиента."""
        logger.debug(f"Looking for active thread for client {client_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id FROM threads 
                WHERE client_id = $1 AND status = $2 
                ORDER BY updated_at DESC LIMIT 1
            """, uuid.UUID(client_id), ThreadStatus.ACTIVE.value)
            if row:
                thread_id = str(row['id'])
                logger.debug(f"Active thread found: {thread_id}")
                return thread_id
            logger.debug("No active thread found")
            return None

    async def create_thread(self, client_id: str) -> str:
        """Создает новый тред."""
        logger.info(f"Creating new thread for client {client_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO threads (client_id, status) VALUES ($1, $2) RETURNING id
            """, uuid.UUID(client_id), ThreadStatus.ACTIVE.value)
            thread_id = str(row['id'])
            logger.info(f"Thread {thread_id} created")
            return thread_id

    async def add_message(self, thread_id: str, role: str, content: str):
        """Сохраняет сообщение в базу."""
        logger.info(f"Adding message to thread {thread_id}, role {role}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO messages (thread_id, role, content)
                VALUES ($1, $2, $3)
            """, uuid.UUID(thread_id), role, content)
            # Обновляем timestamp треда, чтобы он был "свежим"
            await conn.execute("UPDATE threads SET updated_at = NOW() WHERE id = $1", uuid.UUID(thread_id))
            logger.debug(f"Message added and thread updated")

    async def get_messages_for_langgraph(self, thread_id: str) -> List[Dict]:
        """Загружает историю для LangGraph."""
        logger.debug(f"Fetching messages for thread {thread_id}")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content FROM messages 
                WHERE thread_id = $1 ORDER BY created_at ASC
            """, uuid.UUID(thread_id))
            messages = [dict(row) for row in rows]
            logger.debug(f"Retrieved {len(messages)} messages")
            return messages

    async def update_status(self, thread_id: str, status: ThreadStatus) -> None:
        """Обновляет статус треда."""
        logger.info(f"Updating thread {thread_id} status to {status.value}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE threads
                SET status = $1, updated_at = NOW()
                WHERE id = $2
            """, status.value, uuid.UUID(thread_id))

    async def update_manager_chat(self, thread_id: str, manager_chat_id: str) -> None:
        """
        Сохраняет идентификатор менеджера (Telegram chat_id), назначенного для ответа на этот тред.
        Обычно вызывается при эскалации.
        """
        logger.info(f"Assigning manager {manager_chat_id} to thread {thread_id}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE threads
                SET manager_chat_id = $1, updated_at = NOW()
                WHERE id = $2
            """, manager_chat_id, uuid.UUID(thread_id))

    async def find_by_manager_chat(self, manager_chat_id: str) -> List[Dict]:
        """
        Возвращает список активных тредов (status = 'manual'), ожидающих ответа от указанного менеджера.
        """
        logger.info(f"Finding active threads for manager {manager_chat_id}")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, client_id, status, manager_chat_id, created_at, updated_at
                FROM threads
                WHERE manager_chat_id = $1 AND status = 'manual'
                ORDER BY updated_at DESC
            """, manager_chat_id)
            threads = [dict(row) for row in rows]
            logger.info(f"Found {len(threads)} active threads for manager")
            return threads

    async def get_thread_with_project(self, thread_id: str) -> Optional[Dict]:
        """
        Возвращает информацию о треде вместе с project_id клиента.
        Выполняет JOIN с таблицей clients для получения project_id.
        """
        logger.debug(f"Fetching thread with project for thread {thread_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    t.id, t.client_id, t.status, t.manager_chat_id, 
                    t.context_summary, t.created_at, t.updated_at,
                    c.project_id
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.id = $1
            """, uuid.UUID(thread_id))
            if not row:
                logger.warning(f"Thread {thread_id} not found")
                return None
            data = dict(row)
            logger.debug(f"Thread data retrieved for {thread_id}")
            return data

    async def update_summary(self, thread_id: str, summary: str) -> None:
        """
        Обновляет поле context_summary (краткое содержание диалога) для указанного треда.
        """
        logger.info(f"Updating summary for thread {thread_id}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE threads
                SET context_summary = $1, updated_at = NOW()
                WHERE id = $2
            """, summary, uuid.UUID(thread_id))
            logger.debug("Summary updated")
