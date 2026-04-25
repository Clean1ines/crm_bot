"""
Memory repository for long-term user memory.

Stores facts, preferences, and issues per user for cross-conversation recall.
"""

from typing import List, Dict, Any, Optional, Union
import uuid
import asyncpg

from src.domain.project_plane.memory_views import MemoryEntryView
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def _ensure_uuid(value: Union[str, uuid.UUID]) -> uuid.UUID:
    """
    Convert a string or UUID object to a UUID object.
    If the input is already a UUID, return it unchanged.
    """
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


class MemoryRepository:
    """
    Repository for managing user memory (long-term facts).
    
    Each memory entry has a key (e.g., "preferred_discount"), value (JSON),
    and a type for filtering.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the MemoryRepository with a database connection pool.
        
        Args:
            pool: Asyncpg connection pool.
        """
        self.pool = pool
        logger.debug("MemoryRepository initialized")

    async def get_for_user_view(
        self,
        project_id: Union[str, uuid.UUID],
        client_id: Union[str, uuid.UUID],
        *,
        limit: int = 50,
        types: Optional[List[str]] = None
    ) -> List[MemoryEntryView]:
        """
        Retrieve memory entries for a specific user.

        Args:
            project_id: UUID of the project (string or UUID object).
            client_id: UUID of the client (string or UUID object).
            limit: Maximum number of entries to return.
            types: Optional list of types to filter (e.g., ['preference', 'fact']).

        Returns:
            List of dicts with keys: id, key, value, type, created_at, updated_at.
        """
        project_uuid = _ensure_uuid(project_id)
        client_uuid = _ensure_uuid(client_id)

        query = """
            SELECT id, key, value, type, created_at, updated_at
            FROM user_memory
            WHERE project_id = $1 AND client_id = $2
        """
        params = [project_uuid, client_uuid]

        if types:
            placeholders = [f"${i+3}" for i in range(len(types))]
            query += f" AND type IN ({','.join(placeholders)})"
            params.extend(types)

        query += " ORDER BY updated_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        memories = [MemoryEntryView.from_record(dict(r)) for r in rows]
        logger.debug(
            "Loaded %d memory entries for user",
            len(memories),
            extra={"project_id": str(project_id), "client_id": str(client_id)}
        )
        return memories


    async def set(
        self,
        project_id: Union[str, uuid.UUID],
        client_id: Union[str, uuid.UUID],
        key: str,
        value: Any,
        type_: str
    ) -> None:
        """
        Insert or update a memory entry for a user.

        Uses UPSERT: if a memory with same project_id, client_id, key exists,
        it updates the value and updated_at; otherwise inserts.

        Args:
            project_id: UUID of the project (string or UUID object).
            client_id: UUID of the client (string or UUID object).
            key: Memory key (e.g., "preferred_contact").
            value: Any JSON-serializable value.
            type_: Type of memory (e.g., "preference", "fact").
        """
        project_uuid = _ensure_uuid(project_id)
        client_uuid = _ensure_uuid(client_id)

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_memory (project_id, client_id, key, value, type, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (project_id, client_id, key) DO UPDATE
                SET value = EXCLUDED.value,
                    type = EXCLUDED.type,
                    updated_at = NOW()
            """, project_uuid, client_uuid, key, value, type_)

        logger.debug(
            "Memory set",
            extra={"project_id": str(project_id), "client_id": str(client_id), "key": key, "type": type_}
        )

    async def delete(self, project_id: Union[str, uuid.UUID], client_id: Union[str, uuid.UUID], key: str) -> bool:
        """
        Delete a specific memory entry.

        Args:
            project_id: UUID of the project (string or UUID object).
            client_id: UUID of the client (string or UUID object).
            key: Memory key to delete.

        Returns:
            True if deleted, False if not found.
        """
        project_uuid = _ensure_uuid(project_id)
        client_uuid = _ensure_uuid(client_id)

        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM user_memory
                WHERE project_id = $1 AND client_id = $2 AND key = $3
            """, project_uuid, client_uuid, key)
            deleted = result == "DELETE 1"
            if deleted:
                logger.debug(
                    "Memory deleted",
                    extra={"project_id": str(project_id), "client_id": str(client_id), "key": key}
                )
            return deleted

    async def clear_for_user(self, project_id: Union[str, uuid.UUID], client_id: Union[str, uuid.UUID]) -> None:
        """
        Delete all memory for a user (e.g., if user requests data deletion).

        Args:
            project_id: UUID of the project (string or UUID object).
            client_id: UUID of the client (string or UUID object).
        """
        project_uuid = _ensure_uuid(project_id)
        client_uuid = _ensure_uuid(client_id)

        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM user_memory
                WHERE project_id = $1 AND client_id = $2
            """, project_uuid, client_uuid)
        logger.info(
            "All memory cleared for user",
            extra={"project_id": str(project_id), "client_id": str(client_id)}
        )

    async def get_lifecycle(self, project_id: Union[str, uuid.UUID], client_id: Union[str, uuid.UUID]) -> Optional[str]:
        """
        Retrieve the current lifecycle stage for a user from long-term memory.

        Args:
            project_id: UUID of the project (string or UUID object).
            client_id: UUID of the client (string or UUID object).

        Returns:
            Lifecycle stage string (e.g., "cold", "warm", "hot") or None if not set.
        """
        project_uuid = _ensure_uuid(project_id)
        client_uuid = _ensure_uuid(client_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT value
                FROM user_memory
                WHERE project_id = $1 AND client_id = $2 AND type = 'lifecycle' AND key = 'stage'
                ORDER BY updated_at DESC
                LIMIT 1
            """, project_uuid, client_uuid)

        if row:
            # value is JSON, we store as {"stage": "warm"}
            stage = row["value"].get("stage") if isinstance(row["value"], dict) else row["value"]
            if isinstance(stage, str):
                logger.debug(
                    "Retrieved lifecycle",
                    extra={"project_id": str(project_id), "client_id": str(client_id), "lifecycle": stage}
                )
                return stage
        logger.debug("No lifecycle found", extra={"project_id": str(project_id), "client_id": str(client_id)})
        return None

    async def set_lifecycle(self, project_id: Union[str, uuid.UUID], client_id: Union[str, uuid.UUID], lifecycle: str) -> None:
        """
        Store the lifecycle stage for a user in long-term memory.

        Args:
            project_id: UUID of the project (string or UUID object).
            client_id: UUID of the client (string or UUID object).
            lifecycle: Lifecycle stage (e.g., "cold", "warm", "hot").
        """
        # Store as a dict under key 'stage'
        await self.set(project_id, client_id, "stage", {"stage": lifecycle}, "lifecycle")
        logger.info(
            "Lifecycle stored",
            extra={"project_id": str(project_id), "client_id": str(client_id), "lifecycle": lifecycle}
        )

    async def update_by_key(
        self,
        project_id: Union[str, uuid.UUID],
        client_id: Union[str, uuid.UUID],
        key: str,
        value: Any
    ) -> None:
        """
        Update a memory entry by key (preserves type). If the entry does not exist,
        it will be created with a default type 'user_edited'.
        
        Args:
            project_id: UUID of the project (string or UUID object).
            client_id: UUID of the client (string or UUID object).
            key: Memory key to update.
            value: New value (JSON-serializable).
        """
        # Get existing type if present
        project_uuid = _ensure_uuid(project_id)
        client_uuid = _ensure_uuid(client_id)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT type FROM user_memory
                WHERE project_id = $1 AND client_id = $2 AND key = $3
            """, project_uuid, client_uuid, key)
            type_ = row["type"] if row else "user_edited"
        
        await self.set(project_id, client_id, key, value, type_)
        logger.debug(
            "Memory updated by key",
            extra={"project_id": str(project_id), "client_id": str(client_id), "key": key}
        )
