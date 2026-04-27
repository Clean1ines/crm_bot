"""
Event Repository for Event-Sourced Agent Runtime.
"""

import json
from typing import Optional
from uuid import UUID

import asyncpg

from src.domain.project_plane.event_views import EventTimelineItemView
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.manager_reply_history import ManagerReplyHistoryItemView
from src.infrastructure.logging.logger import get_logger


logger = get_logger(__name__)


class EventRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        logger.debug("EventRepository initialized")

    async def append(
        self,
        stream_id: UUID,
        project_id: UUID,
        event_type: str,
        payload: JsonObject,
    ) -> int:
        logger.debug(
            "Appending event",
            extra={
                "stream_id": str(stream_id),
                "project_id": str(project_id),
                "event_type": event_type,
            },
        )

        row = await self.pool.fetchrow(
            """
            INSERT INTO events (stream_id, project_id, event_type, payload)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            stream_id,
            project_id,
            event_type,
            json.dumps(payload),
        )

        event_id = int(row["id"])
        logger.debug(
            "Event appended successfully",
            extra={"event_id": event_id, "event_type": event_type},
        )

        return event_id

    async def get_stream(
        self,
        stream_id: UUID,
        limit: int = 100,
        after_id: Optional[int] = None,
    ) -> list[EventTimelineItemView]:
        logger.debug(
            "Loading event stream",
            extra={
                "stream_id": str(stream_id),
                "limit": limit,
                "after_id": after_id,
            },
        )

        if after_id:
            rows = await self.pool.fetch(
                """
                SELECT id, event_type, payload, created_at
                FROM events
                WHERE stream_id = $1 AND id > $2
                ORDER BY created_at ASC
                LIMIT $3
                """,
                stream_id,
                after_id,
                limit,
            )
        else:
            rows = await self.pool.fetch(
                """
                SELECT id, event_type, payload, created_at
                FROM events
                WHERE stream_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                stream_id,
                limit,
            )

        records = [
            {
                "id": row["id"],
                "type": row["event_type"],
                "payload": row["payload"],
                "ts": row["created_at"],
            }
            for row in rows
        ]

        logger.debug(
            "Event stream loaded",
            extra={"stream_id": str(stream_id), "event_count": len(records)},
        )

        return [EventTimelineItemView.from_record(record) for record in records]

    async def get_by_type(
        self,
        project_id: UUID,
        event_type: str,
        limit: int = 100,
    ) -> list[EventTimelineItemView]:
        logger.debug(
            "Loading events by type",
            extra={
                "project_id": str(project_id),
                "event_type": event_type,
                "limit": limit,
            },
        )

        rows = await self.pool.fetch(
            """
            SELECT id, stream_id, payload, created_at
            FROM events
            WHERE project_id = $1 AND event_type = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            project_id,
            event_type,
            limit,
        )

        records = [
            {
                "id": row["id"],
                "type": event_type,
                "payload": row["payload"],
                "ts": row["created_at"],
                "stream_id": row["stream_id"],
                "project_id": project_id,
            }
            for row in rows
        ]

        logger.debug(
            "Events by type loaded",
            extra={"project_id": str(project_id), "event_count": len(records)},
        )

        return [EventTimelineItemView.from_record(record) for record in records]

    async def get_events_for_thread(
        self,
        thread_id: str,
        limit: int = 30,
        offset: int = 0,
    ) -> list[EventTimelineItemView]:
        logger.debug(
            "Fetching events for thread",
            extra={"thread_id": thread_id, "limit": limit, "offset": offset},
        )

        thread_uuid = UUID(thread_id)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, event_type, payload, created_at
                FROM events
                WHERE stream_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                thread_uuid,
                limit,
                offset,
            )

        records = [
            {
                "id": row["id"],
                "type": row["event_type"],
                "payload": row["payload"],
                "ts": row["created_at"],
            }
            for row in rows
        ]

        logger.debug(
            "Events for thread loaded",
            extra={"thread_id": thread_id, "event_count": len(records)},
        )

        return [EventTimelineItemView.from_record(record) for record in records]

    async def list_for_stream(
        self,
        thread_id: str,
        limit: int = 30,
        offset: int = 0,
    ) -> list[EventTimelineItemView]:
        return await self.get_events_for_thread(thread_id, limit, offset)

    async def get_manager_reply_history(
        self,
        project_id: str,
        manager_user_id: str,
        limit: int = 30,
        offset: int = 0,
    ) -> list[ManagerReplyHistoryItemView]:
        logger.debug(
            "Fetching manager reply history",
            extra={
                "project_id": project_id,
                "manager_user_id": manager_user_id,
                "limit": limit,
                "offset": offset,
            },
        )

        rows = await self.pool.fetch(
            """
            SELECT id, stream_id, project_id, payload, created_at
            FROM events
            WHERE project_id = $1
              AND event_type = 'manager_replied'
              AND payload->>'manager_user_id' = $2
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $4
            """,
            project_id,
            manager_user_id,
            limit,
            offset,
        )

        records = [
            {
                "id": row["id"],
                "stream_id": row["stream_id"],
                "project_id": row["project_id"],
                "payload": row["payload"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

        logger.debug(
            "Manager reply history loaded",
            extra={
                "project_id": project_id,
                "manager_user_id": manager_user_id,
                "reply_count": len(records),
            },
        )

        return [ManagerReplyHistoryItemView.from_record(record) for record in records]
