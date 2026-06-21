from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import asyncpg
import pytest

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_repository_port import (
    WorkItemAttemptDispatchRecord,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_dispatch_repository import (
    PostgresWorkItemAttemptDispatchRepository,
)


class FakeUniqueViolationError(RuntimeError):
    pass


@dataclass(slots=True)
class FakeConnection:
    attempts: dict[str, Mapping[str, object]] = field(default_factory=dict)
    dispatches: dict[str, Mapping[str, object]] = field(default_factory=dict)
    work_item_attempts: set[tuple[str, int]] = field(default_factory=set)
    executed_sql: list[str] = field(default_factory=list)

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.executed_sql.append(query)
        attempt_id = str(args[0])
        return self.dispatches.get(attempt_id)

    async def execute(self, query: str, *args: object) -> str:
        self.executed_sql.append(query)
        if "execution_work_item_attempt_dispatches" in query:
            attempt_id = str(args[0])
            work_item_id = str(args[1])
            attempt_number = _as_int(args[2])
            key = (work_item_id, attempt_number)
            if attempt_id in self.dispatches:
                raise FakeUniqueViolationError("duplicate attempt_id")
            if key in self.work_item_attempts:
                raise FakeUniqueViolationError("duplicate work_item_attempt")
            self.work_item_attempts.add(key)
            self.dispatches[attempt_id] = {
                "attempt_id": attempt_id,
                "work_item_id": work_item_id,
                "attempt_number": attempt_number,
                "lease_token": args[3],
                "worker_ref": args[4],
                "schedule_payload": json.loads(str(args[5])),
                "llm_allocation_payload": json.loads(str(args[6])),
                "dispatch_payload": json.loads(str(args[7])),
            }
            return "INSERT 0 1"

        attempt_id = str(args[0])
        if attempt_id in self.attempts:
            raise FakeUniqueViolationError("duplicate base attempt")
        self.attempts[attempt_id] = {
            "attempt_id": attempt_id,
            "work_item_id": args[1],
            "attempt_number": args[2],
            "started_at": args[3],
        }
        return "INSERT 0 1"


def _started_at() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _record(
    *,
    attempt_id: str = "work-1:attempt:1",
    work_item_id: str = "work-1",
    attempt_number: int = 1,
) -> WorkItemAttemptDispatchRecord:
    return WorkItemAttemptDispatchRecord(
        attempt_id=attempt_id,
        work_item_id=work_item_id,
        attempt_number=attempt_number,
        lease_token="lease-token-1",
        worker_ref="worker-1",
        schedule_payload={"source_unit_ref": "unit-1"},
        llm_allocation_payload={
            "provider": "groq",
            "account_ref": "org-1",
            "model_ref": "qwen-32b",
            "slot_index": 0,
        },
        dispatch_payload={
            "work_item_id": work_item_id,
            "schedule_payload": {"source_unit_ref": "unit-1"},
            "llm_allocation": {
                "provider": "groq",
                "account_ref": "org-1",
                "model_ref": "qwen-32b",
                "slot_index": 0,
            },
        },
        started_at=_started_at(),
    )


def _repository(
    connection: FakeConnection,
) -> PostgresWorkItemAttemptDispatchRepository:
    return PostgresWorkItemAttemptDispatchRepository(
        cast(asyncpg.Connection, connection)
    )


def _as_int(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("expected int")
    return value


@pytest.mark.asyncio
async def test_inserts_base_execution_work_item_attempts_row() -> None:
    connection = FakeConnection()

    await _repository(connection).save_started_dispatch_attempt(_record())

    assert connection.attempts["work-1:attempt:1"] == {
        "attempt_id": "work-1:attempt:1",
        "work_item_id": "work-1",
        "attempt_number": 1,
        "started_at": _started_at(),
    }


@pytest.mark.asyncio
async def test_inserts_execution_work_item_attempt_dispatches_row() -> None:
    connection = FakeConnection()

    await _repository(connection).save_started_dispatch_attempt(_record())

    assert connection.dispatches["work-1:attempt:1"]["schedule_payload"] == {
        "source_unit_ref": "unit-1",
    }
    assert connection.dispatches["work-1:attempt:1"]["llm_allocation_payload"] == {
        "provider": "groq",
        "account_ref": "org-1",
        "model_ref": "qwen-32b",
        "slot_index": 0,
    }


@pytest.mark.asyncio
async def test_duplicate_attempt_id_raises_unique_violation() -> None:
    connection = FakeConnection()
    repository = _repository(connection)

    await repository.save_started_dispatch_attempt(_record())

    with pytest.raises(FakeUniqueViolationError, match="duplicate base attempt"):
        await repository.save_started_dispatch_attempt(_record())


@pytest.mark.asyncio
async def test_duplicate_work_item_and_attempt_number_raises_unique_violation() -> None:
    connection = FakeConnection()
    repository = _repository(connection)

    await repository.save_started_dispatch_attempt(_record(attempt_id="attempt-a"))

    with pytest.raises(FakeUniqueViolationError, match="duplicate work_item_attempt"):
        await repository.save_started_dispatch_attempt(_record(attempt_id="attempt-b"))


def test_no_on_conflict_do_nothing_in_source() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_dispatch_repository.py",
    ).read_text(encoding="utf-8")

    assert "ON CONFLICT" not in source
    assert "DO NOTHING" not in source


def test_no_llm_runtime_imports_or_provider_semantics_in_repository_source() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_dispatch_repository.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "llm_runtime",
        "Groq",
        "qwen",
        "provider",
        "account_ref",
        "model_ref",
        "Prompt",
        "source_unit",
        "artifact_runtime",
        "capacity_runtime",
        "commit(",
        "rollback(",
    )
    for marker in forbidden:
        assert marker not in source
