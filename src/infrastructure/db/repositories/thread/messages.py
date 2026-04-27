from src.domain.project_plane.thread_views import (
    ThreadMessageView,
    ThreadRuntimeMessageView,
)
from src.utils.uuid_utils import ensure_uuid
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class ThreadMessageRepository:
    def __init__(self, pool):
        self.pool = pool

    async def add_message(self, thread_id: str, role: str, content: str) -> None:
        logger.info(f"Adding message to thread {thread_id}, role {role}")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (thread_id, role, content)
                VALUES ($1, $2, $3)
            """,
                ensure_uuid(thread_id),
                role,
                content,
            )

            await conn.execute(
                """
                UPDATE threads
                SET updated_at = NOW()
                WHERE id = $1
            """,
                ensure_uuid(thread_id),
            )

        logger.debug("Message added and thread updated")

    async def append_manager_reply_message(self, thread_id: str, content: str) -> None:
        logger.info("Appending manager reply message", extra={"thread_id": thread_id})

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE threads
                    SET updated_at = NOW()
                    WHERE id = $1
                """,
                    ensure_uuid(thread_id),
                )

                await conn.execute(
                    """
                    INSERT INTO messages (thread_id, role, content)
                    VALUES ($1, $2, $3)
                """,
                    ensure_uuid(thread_id),
                    "assistant",
                    content,
                )

    async def get_messages_for_langgraph(
        self, thread_id: str
    ) -> list[ThreadRuntimeMessageView]:
        logger.debug(f"Fetching messages for thread {thread_id}")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content
                FROM messages
                WHERE thread_id = $1
                ORDER BY created_at ASC
            """,
                ensure_uuid(thread_id),
            )

        messages = [ThreadRuntimeMessageView.from_record(dict(row)) for row in rows]
        logger.debug(f"Retrieved {len(messages)} messages")
        return messages

    async def get_messages(
        self,
        thread_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ThreadMessageView]:
        logger.debug(f"Fetching messages for thread {thread_id}")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, role, content, created_at, metadata
                FROM messages
                WHERE thread_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """,
                ensure_uuid(thread_id),
                limit,
                offset,
            )

        messages = []
        for row in rows:
            created_at = row["created_at"]
            if created_at:
                created_at = created_at.isoformat()

            messages.append(
                ThreadMessageView(
                    id=str(row["id"]),
                    role=row["role"],
                    content=row["content"],
                    created_at=created_at,
                    metadata=row["metadata"] or {},
                )
            )

        messages.reverse()
        logger.debug(f"Retrieved {len(messages)} messages")
        return messages
