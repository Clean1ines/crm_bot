from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.workflow_runtime.application.ports.outbox_repository_port import (
    OutboxRepositoryPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


class PostgresOutboxRepository(OutboxRepositoryPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        row = await self._connection.fetchrow(
            """
            INSERT INTO workflow_runtime_outbox_events (
                event_id,
                event_type,
                workflow_run_id,
                payload,
                occurred_at,
                causation_command_id,
                correlation_id
            )
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
            ON CONFLICT (event_id) DO NOTHING
            RETURNING
                sequence_number,
                event_id,
                event_type,
                workflow_run_id,
                payload,
                occurred_at,
                causation_command_id,
                correlation_id
            """,
            event.event_id.value,
            event.event_type,
            event.workflow_run_id,
            _json_payload(event.payload),
            event.occurred_at,
            event.causation_command_id.value
            if event.causation_command_id is not None
            else None,
            event.correlation_id,
        )
        if row is not None:
            return _hydrate_event(row)

        existing = await self._load_by_event_id(event.event_id)
        if existing is None:
            raise RuntimeError("event_id conflict did not return existing event")
        _assert_idempotent_event_is_same(event, existing)
        return existing

    async def list_events_after(
        self,
        *,
        consumer_ref: WorkflowConsumerRef,
        after_sequence_number: int,
        limit: int,
    ) -> tuple[WorkflowEvent, ...]:
        del consumer_ref
        if after_sequence_number < 0:
            raise ValueError("after_sequence_number must be >= 0")
        if limit <= 0:
            raise ValueError("limit must be > 0")

        rows = await self._connection.fetch(
            """
            SELECT
                sequence_number,
                event_id,
                event_type,
                workflow_run_id,
                payload,
                occurred_at,
                causation_command_id,
                correlation_id
            FROM workflow_runtime_outbox_events
            WHERE sequence_number > $1
            ORDER BY sequence_number ASC
            LIMIT $2
            """,
            after_sequence_number,
            limit,
        )
        return tuple(_hydrate_event(row) for row in rows)

    async def _load_by_event_id(
        self,
        event_id: WorkflowEventId,
    ) -> WorkflowEvent | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                sequence_number,
                event_id,
                event_type,
                workflow_run_id,
                payload,
                occurred_at,
                causation_command_id,
                correlation_id
            FROM workflow_runtime_outbox_events
            WHERE event_id = $1
            """,
            event_id.value,
        )
        if row is None:
            return None
        return _hydrate_event(row)


def _hydrate_event(row: Mapping[str, object]) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(_required_str(row, "event_id")),
        event_type=_required_str(row, "event_type"),
        workflow_run_id=_required_str(row, "workflow_run_id"),
        payload=_required_payload(row, "payload"),
        occurred_at=_required_datetime(row, "occurred_at"),
        causation_command_id=WorkflowCommandId(
            _required_str(row, "causation_command_id")
        )
        if row.get("causation_command_id") is not None
        else None,
        correlation_id=_optional_str(row, "correlation_id"),
        sequence_number=_required_int(row, "sequence_number"),
    )


def _assert_idempotent_event_is_same(
    expected: WorkflowEvent,
    existing: WorkflowEvent,
) -> None:
    if expected.event_type != existing.event_type:
        raise ValueError("event_id conflict has different event_type")
    if expected.workflow_run_id != existing.workflow_run_id:
        raise ValueError("event_id conflict has different workflow_run_id")
    if dict(expected.payload) != dict(existing.payload):
        raise ValueError("event_id conflict has different payload")


def _json_payload(payload: Mapping[str, object]) -> str:
    return json.dumps(dict(payload), default=str, separators=(",", ":"), sort_keys=True)


def _required_payload(row: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = row[key]
    if isinstance(value, str):
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise TypeError(f"{key} must decode to object")
        return decoded
    if isinstance(value, Mapping):
        return value
    raise TypeError(f"{key} must be mapping")


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty string")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be null or non-empty string")
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
