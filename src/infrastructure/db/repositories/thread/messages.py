from collections.abc import Mapping
from src.domain.project_plane.json_types import JsonValue
from src.domain.project_plane.thread_views import (
    ThreadMessageView,
    ThreadRuntimeMessageView,
)
from src.utils.uuid_utils import ensure_uuid
from src.infrastructure.db.repositories.jsonb_payload_hydration import (
    hydrate_jsonb_object_payload,
)
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
                    "manager",
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
                    metadata=_message_metadata(row["metadata"]),
                )
            )

        messages.reverse()
        logger.debug(f"Retrieved {len(messages)} messages")
        return messages


def _message_metadata(value: object) -> dict[str, JsonValue]:
    if value is None:
        return {}

    payload = hydrate_jsonb_object_payload(
        value,
        field_name="messages.metadata",
    )
    return {
        key: _json_value(item, field_name=f"messages.metadata.{key}")
        for key, item in payload.items()
    }


def _json_value(value: object, *, field_name: str) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, list):
        return [_json_value(item, field_name=field_name) for item in value]

    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} must have string keys")
            result[key] = _json_value(item, field_name=f"{field_name}.{key}")
        return result

    raise TypeError(f"{field_name} must be JSON value")
