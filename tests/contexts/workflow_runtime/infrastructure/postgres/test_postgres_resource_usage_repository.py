from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_resource_usage_repository import (
    PostgresResourceUsageRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _usage() -> WorkflowResourceUsageSnapshot:
    return WorkflowResourceUsageSnapshot(
        workflow_run_id="workflow-1",
        request_count=1,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        estimated_cost_microusd=40,
        duration_ms=50,
        provider_breakdown={
            "groq:qwen": {
                "request_count": 1,
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
                "estimated_cost_microusd": 40,
                "duration_ms": 50,
            }
        },
        updated_at=_now(),
    )


class FakeConnection:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "INSERT INTO workflow_runtime_resource_usage_snapshots" in query:
            row = {
                "workflow_run_id": args[0],
                "request_count": args[1],
                "input_tokens": args[2],
                "output_tokens": args[3],
                "total_tokens": args[4],
                "estimated_cost_microusd": args[5],
                "duration_ms": args[6],
                "provider_breakdown": json.loads(_arg_str(args, 7)),
                "updated_at": args[8],
            }
            self.rows[_arg_str(args, 0)] = row
            return row

        if "FROM workflow_runtime_resource_usage_snapshots" in query:
            return self.rows.get(_arg_str(args, 0))

        raise AssertionError(query)


def _arg_str(args: tuple[object, ...], index: int) -> str:
    value = args[index]
    if not isinstance(value, str):
        raise TypeError("expected string argument")
    return value


@pytest.mark.asyncio
async def test_resource_usage_persists_and_reloads() -> None:
    repository = PostgresResourceUsageRepository(
        cast(asyncpg.Connection, FakeConnection())
    )

    saved = await repository.save_usage(_usage())
    loaded = await repository.get_usage("workflow-1")

    assert loaded == saved
    assert saved.provider_breakdown["groq:qwen"]["total_tokens"] == 30
