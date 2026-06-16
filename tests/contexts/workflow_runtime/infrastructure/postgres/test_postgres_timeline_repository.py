from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_timeline_repository import (
    PostgresTimelineRepository,
)


def _time(minute: int) -> datetime:
    return datetime(2026, 6, 11, 12, minute, tzinfo=timezone.utc)


def _entry(entry_id: str, occurred_at: datetime) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=entry_id,
        workflow_run_id="workflow-1",
        event_type="SOURCE_UNITS_CREATED",
        phase="SOURCE_INGESTION",
        severity=WorkflowTimelineSeverity.INFO,
        message="Source units created",
        payload_summary={"entry_id": entry_id},
        occurred_at=occurred_at,
    )


class FakeConnection:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "INSERT INTO workflow_runtime_timeline_entries" not in query:
            raise AssertionError(query)

        timeline_entry_id = _arg_str(args, 0)
        if timeline_entry_id in self.rows:
            if "ON CONFLICT (timeline_entry_id)" not in query:
                raise RuntimeError("duplicate timeline entry was not idempotent")
            return self.rows[timeline_entry_id]

        row = {
            "timeline_entry_id": args[0],
            "workflow_run_id": args[1],
            "event_type": args[2],
            "phase": args[3],
            "severity": args[4],
            "message": args[5],
            "payload_summary": json.loads(_arg_str(args, 6)),
            "occurred_at": args[7],
            "source_ref": args[8],
            "work_item_id": args[9],
            "attempt_id": args[10],
        }
        self.rows[timeline_entry_id] = row
        return row

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        if "FROM workflow_runtime_timeline_entries" not in query:
            raise AssertionError(query)
        workflow_run_id = _arg_str(args, 0)
        limit = _arg_int(args, 1)
        rows = [
            row
            for row in self.rows.values()
            if row["workflow_run_id"] == workflow_run_id
        ]
        return sorted(
            rows,
            key=lambda row: _row_datetime(row, "occurred_at"),
            reverse=True,
        )[:limit]


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


def _row_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise TypeError("expected datetime row value")
    return value


@pytest.mark.asyncio
async def test_timeline_appends_and_lists_recent_entries_ordered_newest_first() -> None:
    repository = PostgresTimelineRepository(cast(asyncpg.Connection, FakeConnection()))

    await repository.append_entry(_entry("entry-1", _time(0)))
    await repository.append_entry(_entry("entry-2", _time(5)))

    listed = await repository.list_recent_entries(
        workflow_run_id="workflow-1",
        limit=10,
    )

    assert tuple(entry.timeline_entry_id for entry in listed) == ("entry-2", "entry-1")


@pytest.mark.asyncio
async def test_timeline_append_is_idempotent_for_existing_entry_id() -> None:
    repository = PostgresTimelineRepository(cast(asyncpg.Connection, FakeConnection()))

    first = await repository.append_entry(_entry("entry-1", _time(0)))
    second = await repository.append_entry(_entry("entry-1", _time(0)))

    assert first.timeline_entry_id == "entry-1"
    assert second.timeline_entry_id == "entry-1"

    listed = await repository.list_recent_entries(
        workflow_run_id="workflow-1",
        limit=10,
    )

    assert tuple(entry.timeline_entry_id for entry in listed) == ("entry-1",)
