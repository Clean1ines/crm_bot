from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
import asyncpg
import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_unit_of_work import (
    PostgresWorkItemSchedulingUnitOfWork,
)


@dataclass(slots=True)
class FakeTransaction:
    started: bool = False
    committed: bool = False
    rolled_back: bool = False

    async def start(self) -> None:
        self.started = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@dataclass(slots=True)
class FakeConnection:
    work_items: dict[str, dict[str, object]] = field(default_factory=dict)
    schedules: dict[str, dict[str, object]] = field(default_factory=dict)
    transaction_obj: FakeTransaction = field(default_factory=FakeTransaction)
    executed_queries: list[str] = field(default_factory=list)

    def transaction(self) -> FakeTransaction:
        return self.transaction_obj

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.executed_queries.append(query)
        work_item_id = str(args[0])
        return self.work_items.get(work_item_id)

    async def fetchval(self, query: str, *args: object) -> object | None:
        self.executed_queries.append(query)
        work_item_id = str(args[0])
        schedule = self.schedules.get(work_item_id)
        if schedule is None:
            return None
        return schedule["payload_hash"]

    async def execute(self, query: str, *args: object) -> str:
        self.executed_queries.append(query)
        if "INSERT INTO execution_work_items" in query:
            work_item_id = str(args[0])
            self.work_items.setdefault(
                work_item_id,
                {
                    "work_item_id": work_item_id,
                    "work_kind": args[1],
                    "status": args[2],
                    "attempt_count": args[3],
                    "leased_by": args[4],
                    "lease_token": args[5],
                    "lease_expires_at": args[6],
                    "next_attempt_at": args[7],
                    "last_error_kind": args[8],
                },
            )
        if "INSERT INTO execution_work_item_schedules" in query:
            work_item_id = str(args[0])
            if work_item_id not in self.schedules:
                self.schedules[work_item_id] = {
                    "work_item_id": work_item_id,
                    "idempotency_key": args[1],
                    "payload_hash": args[2],
                    "payload": json.loads(str(args[3])),
                }
        return "OK"


def _work_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("knowledge_workbench.draft_observation_extraction"),
    )


@pytest.mark.asyncio
async def test_save_scheduled_work_item_and_load_it_back() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresWorkItemSchedulingUnitOfWork(
        cast(asyncpg.Connection, connection)
    )
    item = _work_item()

    await unit_of_work.save_scheduled_work_item(
        item=item,
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"source": "unit-1"},
    )
    await unit_of_work.commit()

    loaded = await PostgresWorkItemSchedulingUnitOfWork(
        cast(asyncpg.Connection, connection),
    ).get_work_item(
        "work-1",
    )

    assert loaded == item
    assert connection.transaction_obj.started
    assert connection.transaction_obj.committed


@pytest.mark.asyncio
async def test_get_schedule_payload_hash_returns_stored_hash() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresWorkItemSchedulingUnitOfWork(
        cast(asyncpg.Connection, connection)
    )
    item = _work_item()

    await unit_of_work.save_scheduled_work_item(
        item=item,
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"source": "unit-1"},
    )

    assert await unit_of_work.get_schedule_payload_hash("work-1") == "hash-1"


@pytest.mark.asyncio
async def test_missing_work_item_returns_none() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresWorkItemSchedulingUnitOfWork(
        cast(asyncpg.Connection, connection)
    )

    assert await unit_of_work.get_work_item("missing") is None


@pytest.mark.asyncio
async def test_duplicate_work_item_id_and_idempotency_key_do_not_corrupt_schedule() -> (
    None
):
    connection = FakeConnection()
    unit_of_work = PostgresWorkItemSchedulingUnitOfWork(
        cast(asyncpg.Connection, connection)
    )
    item = _work_item()

    await unit_of_work.save_scheduled_work_item(
        item=item,
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"source": "unit-1"},
    )
    await unit_of_work.save_scheduled_work_item(
        item=item,
        idempotency_key="idem-1",
        payload_hash="hash-2",
        payload={"source": "unit-2"},
    )

    assert connection.schedules["work-1"]["payload_hash"] == "hash-1"
    assert connection.schedules["work-1"]["payload"] == {"source": "unit-1"}


@pytest.mark.asyncio
async def test_payload_is_stored_as_jsonb_compatible_json() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresWorkItemSchedulingUnitOfWork(
        cast(asyncpg.Connection, connection)
    )

    await unit_of_work.save_scheduled_work_item(
        item=_work_item(),
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"b": 2, "a": 1},
    )

    assert connection.schedules["work-1"]["payload"] == {"a": 1, "b": 2}


def test_implementation_does_not_import_workbench_capacity_llm_or_artifact() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_unit_of_work.py",
    ).read_text(encoding="utf-8")

    forbidden_markers = (
        "knowledge_workbench",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Groq",
        "qwen",
        "DraftObservation",
        "source_unit",
        "Prompt",
    )

    for marker in forbidden_markers:
        assert marker not in source
