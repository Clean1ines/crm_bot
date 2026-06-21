from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_outbox_repository import (
    PostgresOutboxRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str = "event-1",
    event_type: str = "SourceUnitsCreated",
    payload: Mapping[str, object] | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(event_id),
        event_type=event_type,
        workflow_run_id="workflow-1",
        payload={"source_unit_count": 2} if payload is None else payload,
        occurred_at=_now(),
    )


class FakeConnection:
    def __init__(self) -> None:
        self.rows_by_event_id: dict[str, dict[str, object]] = {}
        self.next_sequence_number = 1
        self.notifications: list[tuple[str, str]] = []

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "INSERT INTO workflow_runtime_outbox_events" in query:
            event_id = _arg_str(args, 0)
            if event_id in self.rows_by_event_id:
                return None
            row = {
                "sequence_number": self.next_sequence_number,
                "event_id": args[0],
                "event_type": args[1],
                "workflow_run_id": args[2],
                "payload": json.loads(_arg_str(args, 3)),
                "occurred_at": args[4],
                "causation_command_id": args[5],
                "correlation_id": args[6],
            }
            self.next_sequence_number += 1
            self.rows_by_event_id[event_id] = row
            return row

        if "WHERE event_id = $1" in query:
            return self.rows_by_event_id.get(_arg_str(args, 0))

        raise AssertionError(query)

    async def execute(self, query: str, *args: object) -> str:
        if "pg_notify" not in query:
            raise AssertionError(query)
        self.notifications.append((_arg_str(args, 0), _arg_str(args, 1)))
        return "SELECT 1"

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        if "FROM workflow_runtime_outbox_events" not in query:
            raise AssertionError(query)
        after_sequence_number = _arg_int(args, 0)
        limit = _arg_int(args, 1)
        rows = [
            row
            for row in self.rows_by_event_id.values()
            if _row_int(row, "sequence_number") > after_sequence_number
        ]
        return sorted(rows, key=lambda row: _row_int(row, "sequence_number"))[:limit]


def _arg_str(args: tuple[object, ...], index: int) -> str:
    value = args[index]
    if not isinstance(value, str):
        raise TypeError("expected string argument")
    return value


def _arg_int(args: tuple[object, ...], index: int) -> int:
    value = args[index]
    if not isinstance(value, int):
        raise TypeError("expected int argument")
    return value


def _row_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError("expected int row value")
    return value


@pytest.mark.asyncio
async def test_append_event_assigns_positive_sequence_number() -> None:
    repository = PostgresOutboxRepository(cast(asyncpg.Connection, FakeConnection()))

    saved = await repository.append_event(_event())

    assert saved.sequence_number == 1
    assert saved.event_id == WorkflowEventId("event-1")
    assert saved.payload["source_unit_count"] == 2


@pytest.mark.asyncio
async def test_list_events_after_returns_ordered_events_after_cursor_number() -> None:
    repository = PostgresOutboxRepository(cast(asyncpg.Connection, FakeConnection()))
    first = await repository.append_event(_event(event_id="event-1"))
    second = await repository.append_event(_event(event_id="event-2"))
    third = await repository.append_event(_event(event_id="event-3"))

    assert first.sequence_number == 1
    assert second.sequence_number == 2
    assert third.sequence_number == 3

    listed = await repository.list_events_after(
        consumer_ref=WorkflowConsumerRef("consumer-1"),
        after_sequence_number=1,
        limit=10,
    )

    assert tuple(event.event_id.value for event in listed) == ("event-2", "event-3")


@pytest.mark.asyncio
async def test_append_event_is_idempotent_by_event_id() -> None:
    connection = FakeConnection()
    repository = PostgresOutboxRepository(cast(asyncpg.Connection, connection))

    first = await repository.append_event(_event())
    second = await repository.append_event(_event(event_type="SourceUnitsCreated"))

    assert second == first
    assert tuple(connection.rows_by_event_id) == ("event-1",)


@pytest.mark.asyncio
async def test_append_event_rejects_event_id_payload_mismatch() -> None:
    connection = FakeConnection()
    repository = PostgresOutboxRepository(cast(asyncpg.Connection, connection))

    await repository.append_event(_event())

    with pytest.raises(ValueError, match="different payload"):
        await repository.append_event(_event(payload={"different": True}))
