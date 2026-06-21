from __future__ import annotations

from pathlib import Path

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast
import asyncpg
import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)


@dataclass(slots=True)
class FakeTransaction:
    started: bool = False

    async def start(self) -> None:
        self.started = True


class FakeUniqueViolationError(Exception):
    pass


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
        if "FROM execution_work_item_schedules" in query:
            return self.schedules.get(work_item_id)
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
            if work_item_id in self.work_items:
                raise FakeUniqueViolationError(
                    "duplicate execution_work_items.work_item_id"
                )
            self.work_items[work_item_id] = {
                "work_item_id": work_item_id,
                "work_kind": args[1],
                "status": args[2],
                "attempt_count": args[3],
                "leased_by": args[4],
                "lease_token": args[5],
                "lease_expires_at": args[6],
                "next_attempt_at": args[7],
                "last_error_kind": args[8],
            }
        if "INSERT INTO execution_work_item_schedules" in query:
            work_item_id = str(args[0])
            idempotency_key = str(args[1])
            if work_item_id in self.schedules:
                raise FakeUniqueViolationError(
                    "duplicate execution_work_item_schedules.work_item_id"
                )
            for existing_schedule in self.schedules.values():
                if existing_schedule["idempotency_key"] == idempotency_key:
                    raise FakeUniqueViolationError(
                        "duplicate execution_work_item_schedules.idempotency_key"
                    )
            self.schedules[work_item_id] = {
                "work_item_id": work_item_id,
                "idempotency_key": idempotency_key,
                "payload_hash": args[2],
                "payload": json.loads(str(args[3])),
            }
        return "OK"


def _work_item(work_item_id: str = "work-1") -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        work_kind=WorkKind("knowledge_workbench.claim_builder.section_extraction"),
    )


@pytest.mark.asyncio
async def test_save_scheduled_work_item_and_load_it_back() -> None:
    connection = FakeConnection()
    repository = PostgresWorkItemSchedulingRepository(
        cast(asyncpg.Connection, connection)
    )
    item = _work_item()

    await repository.save_scheduled_work_item(
        item=item,
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"source": "unit-1"},
    )

    loaded = await PostgresWorkItemSchedulingRepository(
        cast(asyncpg.Connection, connection),
    ).get_work_item(
        "work-1",
    )

    assert loaded == item
    assert connection.executed_queries


@pytest.mark.asyncio
async def test_get_schedule_payload_hash_returns_stored_hash() -> None:
    connection = FakeConnection()
    repository = PostgresWorkItemSchedulingRepository(
        cast(asyncpg.Connection, connection)
    )
    item = _work_item()

    await repository.save_scheduled_work_item(
        item=item,
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"source": "unit-1"},
    )

    assert await repository.get_schedule_payload_hash("work-1") == "hash-1"


@pytest.mark.asyncio
async def test_missing_work_item_returns_none() -> None:
    connection = FakeConnection()
    repository = PostgresWorkItemSchedulingRepository(
        cast(asyncpg.Connection, connection)
    )

    assert await repository.get_work_item("missing") is None


@pytest.mark.asyncio
async def test_duplicate_work_item_id_raises_instead_of_silent_ignore() -> None:
    connection = FakeConnection()
    repository = PostgresWorkItemSchedulingRepository(
        cast(asyncpg.Connection, connection)
    )
    item = _work_item()

    await repository.save_scheduled_work_item(
        item=item,
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"source": "unit-1"},
    )

    with pytest.raises(
        FakeUniqueViolationError,
        match="duplicate execution_work_items.work_item_id",
    ):
        await repository.save_scheduled_work_item(
            item=item,
            idempotency_key="idem-1",
            payload_hash="hash-2",
            payload={"source": "unit-2"},
        )

    assert connection.schedules["work-1"]["payload_hash"] == "hash-1"
    assert connection.schedules["work-1"]["payload"] == {"source": "unit-1"}


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_for_different_work_item_raises() -> None:
    connection = FakeConnection()
    repository = PostgresWorkItemSchedulingRepository(
        cast(asyncpg.Connection, connection)
    )

    await repository.save_scheduled_work_item(
        item=_work_item("work-1"),
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"source": "unit-1"},
    )

    with pytest.raises(
        FakeUniqueViolationError,
        match="duplicate execution_work_item_schedules.idempotency_key",
    ):
        await repository.save_scheduled_work_item(
            item=_work_item("work-2"),
            idempotency_key="idem-1",
            payload_hash="hash-2",
            payload={"source": "unit-2"},
        )

    assert connection.schedules["work-1"]["payload_hash"] == "hash-1"
    assert "work-2" not in connection.schedules


@pytest.mark.asyncio
async def test_payload_is_stored_as_jsonb_compatible_json() -> None:
    connection = FakeConnection()
    repository = PostgresWorkItemSchedulingRepository(
        cast(asyncpg.Connection, connection)
    )

    await repository.save_scheduled_work_item(
        item=_work_item(),
        idempotency_key="idem-1",
        payload_hash="hash-1",
        payload={"b": 2, "a": 1},
    )

    assert connection.schedules["work-1"]["payload"] == {"a": 1, "b": 2}


def test_implementation_has_no_silent_conflict_sql() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_repository.py",
    ).read_text(encoding="utf-8")

    assert "ON CONFLICT" not in source
    assert "DO NOTHING" not in source


def test_implementation_does_not_import_workbench_capacity_llm_or_artifact() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_repository.py",
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


def test_postgres_scheduling_repository_has_no_transaction_methods() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_repository.py",
    ).read_text(encoding="utf-8")

    assert "async def commit" not in source
    assert "async def rollback" not in source
    assert "transaction()" not in source


ROOT = Path(__file__).resolve().parents[5]


def test_scheduling_repository_persists_payload_as_jsonb_from_json_dump() -> None:
    content = (
        ROOT / "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_repository.py"
    ).read_text(encoding="utf-8")

    assert "payload_json = json.dumps(" in content
    assert "payload," in content
    assert "$4::jsonb" in content


def test_lease_repository_hydrates_scheduled_jsonb_payload_from_string() -> None:
    content = (
        ROOT / "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_lease_repository.py"
    ).read_text(encoding="utf-8")

    assert "hydrate_jsonb_object_payload" in content
    assert 'field_name="execution_work_item_schedules.payload"' in content
