from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.workflow_runtime.application.ports.command_log_repository_port import (
    CommandLogRepositoryPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


class PostgresCommandLogRepository(CommandLogRepositoryPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        row = await self._connection.fetchrow(
            """
            INSERT INTO workflow_runtime_command_log (
                command_id,
                command_type,
                workflow_run_id,
                idempotency_key,
                payload,
                status,
                run_after,
                created_at,
                updated_at,
                causation_event_id,
                correlation_id,
                attempt_count
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING
                command_id,
                command_type,
                workflow_run_id,
                idempotency_key,
                payload,
                status,
                run_after,
                created_at,
                updated_at,
                causation_event_id,
                correlation_id,
                attempt_count
            """,
            command.command_id.value,
            command.command_type,
            command.workflow_run_id,
            command.idempotency_key.value,
            _json_payload(command.payload),
            command.status.value,
            command.run_after,
            command.created_at,
            command.updated_at,
            command.causation_event_id.value
            if command.causation_event_id is not None
            else None,
            command.correlation_id,
            command.attempt_count,
        )
        if row is not None:
            return _hydrate_command(row)

        existing = await self._load_by_idempotency_key(command.idempotency_key)
        if existing is None:
            raise RuntimeError("idempotency conflict did not return existing command")
        _assert_idempotent_conflict_is_same(command, existing)
        return existing

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        row = await self._connection.fetchrow(
            """
            UPDATE workflow_runtime_command_log
            SET status = $2,
                updated_at = $3
            WHERE command_id = $1
            RETURNING
                command_id,
                command_type,
                workflow_run_id,
                idempotency_key,
                payload,
                status,
                run_after,
                created_at,
                updated_at,
                causation_event_id,
                correlation_id,
                attempt_count
            """,
            command_id.value,
            WorkflowCommandStatus.COMPLETED.value,
            completed_at,
        )
        if row is None:
            raise KeyError(command_id.value)
        return _hydrate_command(row)

    async def mark_command_failed(
        self,
        *,
        command_id: WorkflowCommandId,
        failed_at: datetime,
    ) -> WorkflowCommand:
        row = await self._connection.fetchrow(
            """
            UPDATE workflow_runtime_command_log
            SET status = $2,
                updated_at = $3
            WHERE command_id = $1
            RETURNING
                command_id,
                command_type,
                workflow_run_id,
                idempotency_key,
                payload,
                status,
                run_after,
                created_at,
                updated_at,
                causation_event_id,
                correlation_id,
                attempt_count
            """,
            command_id.value,
            WorkflowCommandStatus.FAILED.value,
            failed_at,
        )
        if row is None:
            raise KeyError(command_id.value)
        return _hydrate_command(row)

    async def reschedule_pending_command(
        self,
        *,
        command_id: WorkflowCommandId,
        run_after: datetime,
        rescheduled_at: datetime,
    ) -> WorkflowCommand:
        row = await self._connection.fetchrow(
            """
            UPDATE workflow_runtime_command_log
            SET status = $2,
                run_after = $3,
                updated_at = $4
            WHERE command_id = $1
            RETURNING
                command_id,
                command_type,
                workflow_run_id,
                idempotency_key,
                payload,
                status,
                run_after,
                created_at,
                updated_at,
                causation_event_id,
                correlation_id,
                attempt_count
            """,
            command_id.value,
            WorkflowCommandStatus.PENDING.value,
            run_after,
            rescheduled_at,
        )
        if row is None:
            raise KeyError(command_id.value)
        return _hydrate_command(row)

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        if not workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty")
        if limit <= 0:
            raise ValueError("limit must be > 0")

        rows = await self._connection.fetch(
            """
            SELECT
                command_id,
                command_type,
                workflow_run_id,
                idempotency_key,
                payload,
                status,
                run_after,
                created_at,
                updated_at,
                causation_event_id,
                correlation_id,
                attempt_count
            FROM workflow_runtime_command_log
            WHERE workflow_run_id = $1
              AND status = $2
              AND run_after <= NOW()
            ORDER BY run_after ASC, created_at ASC
            LIMIT $3
            FOR UPDATE SKIP LOCKED
            """,
            workflow_run_id,
            WorkflowCommandStatus.PENDING.value,
            limit,
        )
        return tuple(_hydrate_command(row) for row in rows)

    async def _load_by_idempotency_key(
        self,
        idempotency_key: WorkflowIdempotencyKey,
    ) -> WorkflowCommand | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                command_id,
                command_type,
                workflow_run_id,
                idempotency_key,
                payload,
                status,
                run_after,
                created_at,
                updated_at,
                causation_event_id,
                correlation_id,
                attempt_count
            FROM workflow_runtime_command_log
            WHERE idempotency_key = $1
            """,
            idempotency_key.value,
        )
        if row is None:
            return None
        return _hydrate_command(row)


def _hydrate_command(row: Mapping[str, object]) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(_required_str(row, "command_id")),
        command_type=_required_str(row, "command_type"),
        workflow_run_id=_required_str(row, "workflow_run_id"),
        idempotency_key=WorkflowIdempotencyKey(_required_str(row, "idempotency_key")),
        payload=_required_payload(row, "payload"),
        status=WorkflowCommandStatus(_required_str(row, "status")),
        run_after=_required_datetime(row, "run_after"),
        created_at=_required_datetime(row, "created_at"),
        updated_at=_required_datetime(row, "updated_at"),
        causation_event_id=WorkflowEventId(_required_str(row, "causation_event_id"))
        if row.get("causation_event_id") is not None
        else None,
        correlation_id=_optional_str(row, "correlation_id"),
        attempt_count=_required_int(row, "attempt_count"),
    )


def _assert_idempotent_conflict_is_same(
    expected: WorkflowCommand,
    existing: WorkflowCommand,
) -> None:
    if expected.command_type != existing.command_type:
        raise ValueError("idempotency_key conflict has different command_type")
    if expected.workflow_run_id != existing.workflow_run_id:
        raise ValueError("idempotency_key conflict has different workflow_run_id")
    if dict(expected.payload) != dict(existing.payload):
        raise ValueError("idempotency_key conflict has different payload")


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
