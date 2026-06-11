from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_command_log_repository import (
    PostgresCommandLogRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _later() -> datetime:
    return datetime(2026, 6, 11, 12, 5, tzinfo=timezone.utc)


def _command(
    *,
    command_id: str = "command-1",
    idempotency_key: str = "source-ingestion:workflow-1",
    payload: Mapping[str, object] | None = None,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(command_id),
        command_type="IngestSourceDocument",
        workflow_run_id="workflow-1",
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={"source_document_ref": "source-document-1"}
        if payload is None
        else payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


class FakeConnection:
    def __init__(self) -> None:
        self.rows_by_command_id: dict[str, dict[str, object]] = {}
        self.idempotency_index: dict[str, str] = {}

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "INSERT INTO workflow_runtime_command_log" in query:
            idempotency_key = _arg_str(args, 3)
            if idempotency_key in self.idempotency_index:
                return None
            row = {
                "command_id": args[0],
                "command_type": args[1],
                "workflow_run_id": args[2],
                "idempotency_key": args[3],
                "payload": json.loads(_arg_str(args, 4)),
                "status": args[5],
                "run_after": args[6],
                "created_at": args[7],
                "updated_at": args[8],
                "causation_event_id": args[9],
                "correlation_id": args[10],
                "attempt_count": args[11],
            }
            command_id = _arg_str(args, 0)
            self.rows_by_command_id[command_id] = row
            self.idempotency_index[idempotency_key] = command_id
            return row

        if "WHERE idempotency_key = $1" in query:
            command_id = self.idempotency_index.get(_arg_str(args, 0))
            if command_id is None:
                return None
            return self.rows_by_command_id[command_id]

        if "UPDATE workflow_runtime_command_log" in query:
            row = self.rows_by_command_id.get(_arg_str(args, 0))
            if row is None:
                return None
            row["status"] = args[1]
            row["updated_at"] = args[2]
            return row

        raise AssertionError(query)


def _arg_str(args: tuple[object, ...], index: int) -> str:
    value = args[index]
    if not isinstance(value, str):
        raise TypeError("expected string argument")
    return value


@pytest.mark.asyncio
async def test_append_pending_command_persists_command() -> None:
    repository = PostgresCommandLogRepository(
        cast(asyncpg.Connection, FakeConnection())
    )

    saved = await repository.append_pending_command(_command())

    assert saved.command_id == WorkflowCommandId("command-1")
    assert saved.command_type == "IngestSourceDocument"
    assert saved.status is WorkflowCommandStatus.PENDING
    assert saved.payload["source_document_ref"] == "source-document-1"


@pytest.mark.asyncio
async def test_append_pending_command_is_idempotent_by_idempotency_key() -> None:
    connection = FakeConnection()
    repository = PostgresCommandLogRepository(cast(asyncpg.Connection, connection))

    first = await repository.append_pending_command(_command())
    second = await repository.append_pending_command(
        _command(command_id="command-2"),
    )

    assert second == first
    assert tuple(connection.rows_by_command_id) == ("command-1",)


@pytest.mark.asyncio
async def test_append_pending_command_rejects_idempotency_payload_mismatch() -> None:
    connection = FakeConnection()
    repository = PostgresCommandLogRepository(cast(asyncpg.Connection, connection))

    await repository.append_pending_command(_command())

    with pytest.raises(ValueError, match="different payload"):
        await repository.append_pending_command(
            _command(command_id="command-2", payload={"different": True})
        )


@pytest.mark.asyncio
async def test_mark_command_completed_marks_command_completed() -> None:
    connection = FakeConnection()
    repository = PostgresCommandLogRepository(cast(asyncpg.Connection, connection))
    saved = await repository.append_pending_command(_command())

    completed = await repository.mark_command_completed(
        command_id=saved.command_id,
        completed_at=_later(),
    )

    assert completed.status is WorkflowCommandStatus.COMPLETED
    assert completed.updated_at == _later()
