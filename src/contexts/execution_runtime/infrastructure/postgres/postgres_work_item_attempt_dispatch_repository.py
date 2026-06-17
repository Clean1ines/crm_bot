from __future__ import annotations

import json
from collections.abc import Mapping

import asyncpg

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_repository_port import (
    WorkItemAttemptDispatchRecord,
    WorkItemAttemptDispatchRepositoryPort,
)


class PostgresWorkItemAttemptDispatchRepository(WorkItemAttemptDispatchRepositoryPort):
    """Persists started execution attempt records and generic dispatch metadata.

    Transaction ownership belongs to the composing application boundary.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def save_started_dispatch_attempt(
        self,
        record: WorkItemAttemptDispatchRecord,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO execution_work_item_attempts (
                attempt_id,
                work_item_id,
                attempt_number,
                started_at
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT (attempt_id) DO NOTHING
            """,
            record.attempt_id,
            record.work_item_id,
            record.attempt_number,
            record.started_at,
        )
        await self._connection.execute(
            """
            INSERT INTO execution_work_item_attempt_dispatches (
                attempt_id,
                work_item_id,
                attempt_number,
                lease_token,
                worker_ref,
                schedule_payload,
                llm_allocation_payload,
                dispatch_payload
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb)
            ON CONFLICT (attempt_id) DO NOTHING
            """,
            record.attempt_id,
            record.work_item_id,
            record.attempt_number,
            record.lease_token,
            record.worker_ref,
            _jsonb(record.schedule_payload),
            _jsonb(record.llm_allocation_payload),
            _jsonb(record.dispatch_payload),
        )

        existing_dispatch = await self._connection.fetchrow(
            """
            SELECT
                attempt_id,
                work_item_id,
                attempt_number,
                lease_token,
                worker_ref,
                schedule_payload,
                llm_allocation_payload,
                dispatch_payload
            FROM execution_work_item_attempt_dispatches
            WHERE attempt_id = $1
            """,
            record.attempt_id,
        )
        if existing_dispatch is None:
            raise RuntimeError(
                "started dispatch attempt was saved without dispatch row"
            )

        _assert_started_dispatch_attempt_is_same(record, existing_dispatch)


def _jsonb(payload: Mapping[str, object]) -> str:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))


def _assert_started_dispatch_attempt_is_same(
    expected: WorkItemAttemptDispatchRecord,
    existing: Mapping[str, object],
) -> None:
    if _required_str(existing, "work_item_id") != expected.work_item_id:
        raise ValueError(
            "attempt dispatch idempotency conflict has different work_item_id"
        )

    existing_attempt_number = existing["attempt_number"]
    if not isinstance(existing_attempt_number, int):
        raise TypeError("attempt_number must be int")
    if existing_attempt_number != expected.attempt_number:
        raise ValueError(
            "attempt dispatch idempotency conflict has different attempt_number"
        )

    if _required_str(existing, "lease_token") != expected.lease_token:
        raise ValueError(
            "attempt dispatch idempotency conflict has different lease_token"
        )
    if _required_str(existing, "worker_ref") != expected.worker_ref:
        raise ValueError(
            "attempt dispatch idempotency conflict has different worker_ref"
        )

    if _canonical_payload(existing["schedule_payload"]) != _jsonb(
        expected.schedule_payload
    ):
        raise ValueError(
            "attempt dispatch idempotency conflict has different schedule_payload"
        )
    if _canonical_payload(existing["llm_allocation_payload"]) != _jsonb(
        expected.llm_allocation_payload
    ):
        raise ValueError(
            "attempt dispatch idempotency conflict has different llm_allocation_payload"
        )
    if _canonical_payload(existing["dispatch_payload"]) != _jsonb(
        expected.dispatch_payload
    ):
        raise ValueError(
            "attempt dispatch idempotency conflict has different dispatch_payload"
        )


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be non-empty string")
    return value


def _canonical_payload(value: object) -> str:
    if isinstance(value, str):
        decoded: object = json.loads(value)
    elif isinstance(value, Mapping):
        decoded = value
    else:
        raise TypeError("json payload must be mapping or string")

    if not isinstance(decoded, Mapping):
        raise TypeError("json payload must decode to object")

    return json.dumps(
        dict(decoded),
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )
