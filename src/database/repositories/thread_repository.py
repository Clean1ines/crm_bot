import uuid
import json
from typing import List, Optional, Dict, Any
from ..models import ThreadStatus
from src.core.logging import get_logger
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)

class ThreadRepository:
    def __init__(self, pool):
        """
        Принимает пул соединений asyncpg.
        """
        self.pool = pool

    async def get_or_create_client(self, project_id: str, chat_id: int, username: str = None, source: str = "telegram") -> str:
        """Возвращает UUID клиента, создавая его при необходимости."""
        logger.info(f"Getting or creating client for project {project_id}, chat {chat_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO clients (project_id, chat_id, username, source)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (project_id, chat_id) DO UPDATE SET username = EXCLUDED.username
                RETURNING id
            """, ensure_uuid(project_id), chat_id, username, source)
            client_id = str(row['id'])
            logger.info(f"Client {client_id} ensured")
            return client_id

    async def get_active_thread(self, client_id: str) -> Optional[str]:
        """
        Ищет последний тред клиента (независимо от статуса), чтобы не создавать новый при наличии ручного.
        Возвращает ID последнего треда по updated_at.
        """
        logger.debug(f"Looking for thread for client {client_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id FROM threads 
                WHERE client_id = $1
                ORDER BY updated_at DESC LIMIT 1
            """, ensure_uuid(client_id))
            if row:
                thread_id = str(row['id'])
                logger.debug(f"Thread found: {thread_id}")
                return thread_id
            logger.debug("No thread found")
            return None

    async def create_thread(self, client_id: str) -> str:
        """Создает новый тред со статусом ACTIVE."""
        logger.info(f"Creating new thread for client {client_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO threads (client_id, status) VALUES ($1, $2) RETURNING id
            """, ensure_uuid(client_id), ThreadStatus.ACTIVE.value)
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
            """, ensure_uuid(thread_id), role, content)
            # Обновляем timestamp треда, чтобы он был "свежим"
            await conn.execute("UPDATE threads SET updated_at = NOW() WHERE id = $1", ensure_uuid(thread_id))
            logger.debug(f"Message added and thread updated")

    async def get_messages_for_langgraph(self, thread_id: str) -> List[Dict]:
        """Загружает историю для LangGraph."""
        logger.debug(f"Fetching messages for thread {thread_id}")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content FROM messages 
                WHERE thread_id = $1 ORDER BY created_at ASC
            """, ensure_uuid(thread_id))
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
            """, status.value, ensure_uuid(thread_id))

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
            """, manager_chat_id, ensure_uuid(thread_id))

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
            """, ensure_uuid(thread_id))
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
            """, summary, ensure_uuid(thread_id))
            logger.debug("Summary updated")

    async def get_state_json(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает сохранённое состояние графа (state_json) для указанного треда.
        Если состояние отсутствует, возвращает None.
        """
        logger.debug(f"Fetching state_json for thread {thread_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT state_json FROM threads WHERE id = $1
            """, ensure_uuid(thread_id))
            if row and row["state_json"] is not None:
                state = row["state_json"]
                logger.debug(f"State_json retrieved for thread {thread_id}")
                return state
            logger.debug(f"No state_json found for thread {thread_id}")
            return None

    async def save_state_json(self, thread_id: str, state: Dict[str, Any]) -> None:
        """
        Сохраняет состояние графа (state_json) для указанного треда.
        Перезаписывает существующее состояние.
        """
        logger.info(f"Saving state_json for thread {thread_id}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE threads
                SET state_json = $1, updated_at = NOW()
                WHERE id = $2
            """, json.dumps(state, ensure_ascii=False), ensure_uuid(thread_id))
            logger.debug("State_json saved")

    async def update_analytics(
        self,
        thread_id: str,
        intent: Optional[str] = None,
        lifecycle: Optional[str] = None,
        cta: Optional[str] = None,
        decision: Optional[str] = None
    ) -> None:
        """
        Обновляет аналитические поля треда: intent, lifecycle, cta, decision.

        Args:
            thread_id: UUID треда.
            intent: Распознанное намерение (например, "pricing", "support").
            lifecycle: Стадия жизненного цикла (например, "cold", "warm", "hot").
            cta: Тип призыва к действию (например, "request_demo").
            decision: Решение роутера (например, "RESPOND_KB").
        """
        thread_uuid = ensure_uuid(thread_id)

        # Build SET clause dynamically
        updates = []
        params = []
        if intent is not None:
            updates.append("intent = $%d" % (len(params) + 1))
            params.append(intent)
        if lifecycle is not None:
            updates.append("lifecycle = $%d" % (len(params) + 1))
            params.append(lifecycle)
        if cta is not None:
            updates.append("cta = $%d" % (len(params) + 1))
            params.append(cta)
        if decision is not None:
            updates.append("decision = $%d" % (len(params) + 1))
            params.append(decision)

        if not updates:
            logger.debug("No analytics fields to update", extra={"thread_id": thread_id})
            return

        query = f"""
            UPDATE threads
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = ${len(params) + 1}
        """
        params.append(thread_uuid)

        async with self.pool.acquire() as conn:
            await conn.execute(query, *params)

        logger.info(
            "Analytics updated",
            extra={
                "thread_id": thread_id,
                "intent": intent,
                "lifecycle": lifecycle,
                "cta": cta,
                "decision": decision
            }
        )

    async def get_analytics(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает аналитические поля треда: intent, lifecycle, cta, decision.

        Args:
            thread_id: UUID треда.

        Returns:
            Словарь с ключами intent, lifecycle, cta, decision или None, если тред не найден.
        """
        logger.debug(f"Fetching analytics for thread {thread_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT intent, lifecycle, cta, decision
                FROM threads
                WHERE id = $1
            """, ensure_uuid(thread_id))
            if not row:
                logger.warning(f"Thread {thread_id} not found for analytics fetch")
                return None
            analytics = {
                "intent": row["intent"],
                "lifecycle": row["lifecycle"],
                "cta": row["cta"],
                "decision": row["decision"]
            }
            logger.debug(f"Analytics retrieved for thread {thread_id}")
            return analytics

    async def get_message_counts(self, thread_id: str) -> Dict[str, int]:
        """
        Возвращает количество сообщений по ролям для треда.
        
        Args:
            thread_id: UUID треда.
        
        Returns:
            Словарь с ключами total, ai, manager.
        """
        logger.debug(f"Fetching message counts for thread {thread_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN role = 'assistant' THEN 1 END) as ai,
                    COUNT(CASE WHEN role = 'user' THEN 1 END) as manager  -- manager messages are 'user' role from manager bot
                FROM messages
                WHERE thread_id = $1
            """, ensure_uuid(thread_id))
            return {
                "total": row["total"] or 0,
                "ai": row["ai"] or 0,
                "manager": row["manager"] or 0
            }

    async def get_dialogs(
        self,
        project_id: str,
        limit: int = 20,
        offset: int = 0,
        status_filter: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Возвращает список диалогов (тредов) с дополнительными полями:
        - thread id, status, interaction_mode, updated_at, created_at
        - client id, full_name, username, chat_id
        - last_message content and created_at
        - unread_count (optional, placeholder)
        """
        logger.info("Fetching dialogs", extra={"project_id": project_id, "limit": limit, "offset": offset})
        
        # Build WHERE clause
        where_parts = ["c.project_id = $1"]
        params = [ensure_uuid(project_id)]
        param_idx = 2
        
        if status_filter:
            where_parts.append(f"t.status = ${param_idx}")
            params.append(status_filter)
            param_idx += 1
        
        if search:
            where_parts.append(f"(c.full_name ILIKE $${param_idx} OR c.username ILIKE $${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1
        
        where_clause = " AND ".join(where_parts)
        
        # Query with last message subquery
        query = f"""
            SELECT
                t.id AS thread_id,
                t.status,
                t.interaction_mode,
                t.created_at AS thread_created_at,
                t.updated_at AS thread_updated_at,
                c.id AS client_id,
                c.full_name,
                c.username,
                c.chat_id,
                lm.content AS last_message_content,
                lm.created_at AS last_message_created_at
            FROM threads t
            JOIN clients c ON t.client_id = c.id
            LEFT JOIN LATERAL (
                SELECT content, created_at
                FROM messages m
                WHERE m.thread_id = t.id
                ORDER BY m.created_at DESC
                LIMIT 1
            ) lm ON true
            WHERE {where_clause}
            ORDER BY t.updated_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        dialogs = []
        for row in rows:
            # Convert datetime objects to ISO format strings
            thread_created_at = row["thread_created_at"]
            if thread_created_at:
                thread_created_at = thread_created_at.isoformat()
            thread_updated_at = row["thread_updated_at"]
            if thread_updated_at:
                thread_updated_at = thread_updated_at.isoformat()
            last_msg_created_at = row["last_message_created_at"]
            if last_msg_created_at:
                last_msg_created_at = last_msg_created_at.isoformat()

            dialogs.append({
                "thread_id": str(row["thread_id"]),
                "status": row["status"],
                "interaction_mode": row["interaction_mode"],
                "thread_created_at": thread_created_at,
                "thread_updated_at": thread_updated_at,
                "client": {
                    "id": str(row["client_id"]),
                    "full_name": row["full_name"],
                    "username": row["username"],
                    "chat_id": row["chat_id"]
                },
                "last_message": {
                    "content": row["last_message_content"],
                    "created_at": last_msg_created_at
                } if row["last_message_content"] else None,
                "unread_count": 0  # placeholder
            })
        
        logger.debug(f"Retrieved {len(dialogs)} dialogs")
        return dialogs

    async def get_messages(self, thread_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Возвращает сообщения треда с пагинацией.
        """
        logger.debug(f"Fetching messages for thread {thread_id}")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, role, content, created_at, metadata
                FROM messages
                WHERE thread_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """, ensure_uuid(thread_id), limit, offset)
        
        messages = []
        for row in rows:
            created_at = row["created_at"]
            if created_at:
                created_at = created_at.isoformat()
            messages.append({
                "id": str(row["id"]),
                "role": row["role"],
                "content": row["content"],
                "created_at": created_at,
                "metadata": row["metadata"] or {}
            })
        
        messages.reverse()  # chronological order for display
        logger.debug(f"Retrieved {len(messages)} messages")
        return messages

    async def update_interaction_mode(self, thread_id: str, mode: str) -> None:
        """
        Обновляет interaction_mode треда.
        """
        logger.info(f"Updating interaction mode for thread {thread_id} to {mode}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE threads
                SET interaction_mode = $1, updated_at = NOW()
                WHERE id = $2
            """, mode, ensure_uuid(thread_id))

    # В ThreadRepository:

    async def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Возвращает все треды с указанным статусом."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT t.*, c.name as client_name
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.status = $1
                ORDER BY t.updated_at DESC
            """, status)
            return [dict(row) for row in rows]
