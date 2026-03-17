"""
Event Repository for Event-Sourced Agent Runtime.

This module provides data access methods for the events table,
which serves as the source of truth for all conversation state changes.
"""

import json
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

from src.core.logging import get_logger

logger = get_logger(__name__)


class EventRepository:
    """
    Repository for managing event store operations.
    
    The EventRepository handles appending events to the event stream
    and retrieving events for state reconstruction. This follows the
    Event Sourcing pattern where all state changes are recorded as
    immutable events.
    
    Attributes:
        pool: Asyncpg connection pool for database operations.
    """
    
    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the EventRepository with a database connection pool.
        
        Args:
            pool: Asyncpg connection pool for database operations.
        """
        self.pool = pool
        logger.debug("EventRepository initialized")
    
    async def append(
        self,
        stream_id: UUID,
        project_id: UUID,
        event_type: str,
        payload: Dict[str, Any]
    ) -> int:
        """
        Append a new event to the event stream.
        
        This method records a state-changing event in the event store.
        Events are immutable and should never be updated or deleted.
        
        Args:
            stream_id: The conversation/thread ID (groups events by dialogue).
            project_id: The project ID for multi-tenant isolation.
            event_type: Type of event (e.g., 'message_received', 'ai_replied').
            payload: Event-specific data as a dictionary.
        
        Returns:
            The ID of the newly created event.
        
        Example:
            >>> await repo.append(
            ...     stream_id=thread_id,
            ...     project_id=project_id,
            ...     event_type='message_received',
            ...     payload={'user_id': 123, 'text': 'Hello'}
            ... )
        """
        logger.debug(
            "Appending event",
            extra={
                "stream_id": str(stream_id),
                "project_id": str(project_id),
                "event_type": event_type
            }
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
            json.dumps(payload)
        )
        
        event_id = row["id"]
        logger.debug(
            "Event appended successfully",
            extra={"event_id": event_id, "event_type": event_type}
        )
        
        return event_id
    
    async def get_stream(
        self,
        stream_id: UUID,
        limit: int = 100,
        after_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events from a specific stream for state reconstruction.
        
        This method loads events in chronological order to rebuild
        the conversation state. Supports pagination via after_id.
        
        Args:
            stream_id: The conversation/thread ID to load events for.
            limit: Maximum number of events to return (default: 100).
            after_id: Only return events with ID greater than this value.
        
        Returns:
            List of events with type, payload, and timestamp.
        
        Example:
            >>> events = await repo.get_stream(thread_id, limit=50)
            >>> for event in events:
            ...     state = apply_event(state, event)
        """
        logger.debug(
            "Loading event stream",
            extra={
                "stream_id": str(stream_id),
                "limit": limit,
                "after_id": after_id
            }
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
                limit
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
                limit
            )
        
        events = [
            {
                "id": row["id"],
                "type": row["event_type"],
                "payload": row["payload"],
                "ts": row["created_at"]
            }
            for row in rows
        ]
        
        logger.debug(
            "Event stream loaded",
            extra={"stream_id": str(stream_id), "event_count": len(events)}
        )
        
        return events
    
    async def get_by_type(
        self,
        project_id: UUID,
        event_type: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events of a specific type for analytics.
        
        This method is useful for generating metrics and reports
        based on event types (e.g., count of escalations).
        
        Args:
            project_id: The project ID to filter events.
            event_type: The type of events to retrieve.
            limit: Maximum number of events to return.
        
        Returns:
            List of events matching the criteria.
        """
        logger.debug(
            "Loading events by type",
            extra={
                "project_id": str(project_id),
                "event_type": event_type,
                "limit": limit
            }
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
            limit
        )
        
        events = [
            {
                "id": row["id"],
                "stream_id": row["stream_id"],
                "payload": row["payload"],
                "ts": row["created_at"]
            }
            for row in rows
        ]
        
        logger.debug(
            "Events by type loaded",
            extra={"project_id": str(project_id), "event_count": len(events)}
        )
        
        return events
