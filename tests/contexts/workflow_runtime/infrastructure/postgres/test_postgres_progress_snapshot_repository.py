from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_progress_snapshot_repository import (
    PostgresProgressSnapshotRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _snapshot() -> WorkflowProgressSnapshot:
    return WorkflowProgressSnapshot(
        workflow_run_id="workflow-1",
        current_phase="SOURCE_INGESTION",
        workflow_status="RUNNING",
        total_work_items=2,
        scheduled_work_items=2,
        domain_counters={"source_units": 2},
        updated_at=_now(),
    )


class FakeConnection:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "INSERT INTO workflow_runtime_progress_snapshots" in query:
            row = {
                "workflow_run_id": args[0],
                "current_phase": args[1],
                "workflow_status": args[2],
                "total_work_items": args[3],
                "scheduled_work_items": args[4],
                "running_work_items": args[5],
                "completed_work_items": args[6],
                "deferred_work_items": args[7],
                "retryable_failed_work_items": args[8],
                "terminal_failed_work_items": args[9],
                "blocked_work_items": args[10],
                "domain_counters": json.loads(_arg_str(args, 11)),
                "started_at": args[12],
                "updated_at": args[13],
                "completed_at": args[14],
            }
            self.rows[_arg_str(args, 0)] = row
            return row

        if "FROM workflow_runtime_progress_snapshots" in query:
            return self.rows.get(_arg_str(args, 0))

        raise AssertionError(query)


def _arg_str(args: tuple[object, ...], index: int) -> str:
    value = args[index]
    if not isinstance(value, str):
        raise TypeError("expected string argument")
    return value


@pytest.mark.asyncio
async def test_progress_snapshot_persists_and_reloads() -> None:
    repository = PostgresProgressSnapshotRepository(
        cast(asyncpg.Connection, FakeConnection())
    )

    saved = await repository.save_snapshot(_snapshot())
    loaded = await repository.get_snapshot("workflow-1")

    assert loaded == saved
    assert saved.domain_counters["source_units"] == 2
