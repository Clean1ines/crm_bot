from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.workflow_runtime.application.ports.event_cursor_repository_port import (
    EventCursorRepositoryPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event_cursor import (
    WorkflowEventCursor,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)


class PostgresEventCursorRepository(EventCursorRepositoryPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def get_cursor(
        self,
        consumer_ref: WorkflowConsumerRef,
    ) -> WorkflowEventCursor | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                consumer_ref,
                last_seen_sequence_number,
                updated_at
            FROM workflow_runtime_event_cursors
            WHERE consumer_ref = $1
            """,
            consumer_ref.value,
        )
        if row is None:
            return None
        return _hydrate_cursor(row)

    async def save_cursor(
        self,
        cursor: WorkflowEventCursor,
    ) -> WorkflowEventCursor:
        existing = await self.get_cursor(cursor.consumer_ref)
        effective_cursor = cursor
        if existing is not None:
            effective_cursor = existing.advance_to(
                cursor.last_seen_sequence_number,
                updated_at=cursor.updated_at,
            )

        row = await self._connection.fetchrow(
            """
            INSERT INTO workflow_runtime_event_cursors (
                consumer_ref,
                last_seen_sequence_number,
                updated_at
            )
            VALUES ($1, $2, $3)
            ON CONFLICT (consumer_ref) DO UPDATE
            SET last_seen_sequence_number = EXCLUDED.last_seen_sequence_number,
                updated_at = EXCLUDED.updated_at
            RETURNING
                consumer_ref,
                last_seen_sequence_number,
                updated_at
            """,
            effective_cursor.consumer_ref.value,
            effective_cursor.last_seen_sequence_number,
            effective_cursor.updated_at,
        )
        if row is None:
            raise RuntimeError("cursor upsert did not return row")
        return _hydrate_cursor(row)


def _hydrate_cursor(row: Mapping[str, object]) -> WorkflowEventCursor:
    return WorkflowEventCursor(
        consumer_ref=WorkflowConsumerRef(_required_str(row, "consumer_ref")),
        last_seen_sequence_number=_required_int(row, "last_seen_sequence_number"),
        updated_at=_required_datetime(row, "updated_at"),
    )


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty string")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value
