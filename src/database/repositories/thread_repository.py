import uuid
from typing import List, Optional, Dict
from ..models import ThreadStatus, MessageRole

class ThreadRepository:
    def __init__(self, pool):
        """
        Принимает пул соединений asyncpg.
        """
        self.pool = pool

    async def get_or_create_client(self, project_id: str, chat_id: str, username: str = None) -> str:
        """Возвращает UUID клиента, создавая его при необходимости."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO clients (project_id, chat_id, username)
                VALUES ($1, $2, $3)
                ON CONFLICT (project_id, chat_id) DO UPDATE SET username = EXCLUDED.username
                RETURNING id
            """, uuid.UUID(project_id), str(chat_id), username)
            return str(row['id'])

    async def get_active_thread(self, client_id: str) -> Optional[str]:
        """Ищет последний активный тред клиента."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id FROM threads 
                WHERE client_id = $1 AND status = $2 
                ORDER BY updated_at DESC LIMIT 1
            """, uuid.UUID(client_id), ThreadStatus.ACTIVE.value)
            return str(row['id']) if row else None

    async def create_thread(self, client_id: str) -> str:
        """Создает новый тред."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO threads (client_id, status) VALUES ($1, $2) RETURNING id
            """, uuid.UUID(client_id), ThreadStatus.ACTIVE.value)
            return str(row['id'])

    async def add_message(self, thread_id: str, role: MessageRole, content: str):
        """Сохраняет сообщение в базу."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO messages (thread_id, role, content)
                VALUES ($1, $2, $3)
            """, uuid.UUID(thread_id), role.value, content)
            # Обновляем timestamp треда, чтобы он был "свежим"
            await conn.execute("UPDATE threads SET updated_at = NOW() WHERE id = $1", uuid.UUID(thread_id))

    async def get_messages_for_langgraph(self, thread_id: str) -> List[Dict]:
        """Загружает историю для LangGraph."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content FROM messages 
                WHERE thread_id = $1 ORDER BY created_at ASC
            """, uuid.UUID(thread_id))
            return [dict(row) for row in rows]

    async def update_status(self, thread_id: str, status: ThreadStatus) -> None:
        """Обновляет статус треда."""
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
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, client_id, status, manager_chat_id, created_at, updated_at
                FROM threads
                WHERE manager_chat_id = $1 AND status = 'manual'
                ORDER BY updated_at DESC
            """, manager_chat_id)
            return [dict(row) for row in rows]

    # NEW METHOD
    async def get_thread_with_project(self, thread_id: str) -> Optional[Dict]:
        """
        Возвращает информацию о треде вместе с project_id клиента.
        Выполняет JOIN с таблицей clients для получения project_id.
        """
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
                return None
            return dict(row)
