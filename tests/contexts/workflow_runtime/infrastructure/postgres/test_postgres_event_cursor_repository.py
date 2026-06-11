from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_event_cursor import (
    WorkflowEventCursor,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_event_cursor_repository import (
    PostgresEventCursorRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _later() -> datetime:
    return datetime(2026, 6, 11, 12, 5, tzinfo=timezone.utc)


def _cursor(
    *,
    sequence_number: int = 1,
    updated_at: datetime | None = None,
) -> WorkflowEventCursor:
    return WorkflowEventCursor(
        consumer_ref=WorkflowConsumerRef("consumer-1"),
        last_seen_sequence_number=sequence_number,
        updated_at=_now() if updated_at is None else updated_at,
    )


class FakeConnection:
    def __init__(self) -> None:
        self.rows_by_consumer_ref: dict[str, dict[str, object]] = {}

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "SELECT" in query and "FROM workflow_runtime_event_cursors" in query:
            return self.rows_by_consumer_ref.get(_arg_str(args, 0))

        if "INSERT INTO workflow_runtime_event_cursors" in query:
            row = {
                "consumer_ref": args[0],
                "last_seen_sequence_number": args[1],
                "updated_at": args[2],
            }
            self.rows_by_consumer_ref[_arg_str(args, 0)] = row
            return row

        raise AssertionError(query)


def _arg_str(args: tuple[object, ...], index: int) -> str:
    value = args[index]
    if not isinstance(value, str):
        raise TypeError("expected string argument")
    return value


@pytest.mark.asyncio
async def test_get_cursor_returns_none_for_missing_cursor() -> None:
    repository = PostgresEventCursorRepository(
        cast(asyncpg.Connection, FakeConnection())
    )

    assert await repository.get_cursor(WorkflowConsumerRef("missing")) is None


@pytest.mark.asyncio
async def test_save_cursor_inserts_cursor() -> None:
    repository = PostgresEventCursorRepository(
        cast(asyncpg.Connection, FakeConnection())
    )

    saved = await repository.save_cursor(_cursor(sequence_number=1))

    assert saved.consumer_ref == WorkflowConsumerRef("consumer-1")
    assert saved.last_seen_sequence_number == 1


@pytest.mark.asyncio
async def test_save_cursor_updates_cursor_forward() -> None:
    repository = PostgresEventCursorRepository(
        cast(asyncpg.Connection, FakeConnection())
    )

    await repository.save_cursor(_cursor(sequence_number=1))
    saved = await repository.save_cursor(
        _cursor(sequence_number=3, updated_at=_later())
    )

    assert saved.last_seen_sequence_number == 3
    assert saved.updated_at == _later()


@pytest.mark.asyncio
async def test_domain_rejects_backwards_cursor_advance() -> None:
    repository = PostgresEventCursorRepository(
        cast(asyncpg.Connection, FakeConnection())
    )

    await repository.save_cursor(_cursor(sequence_number=3))

    with pytest.raises(ValueError, match="cannot move cursor backwards"):
        await repository.save_cursor(_cursor(sequence_number=2))
