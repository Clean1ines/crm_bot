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
            ) VALUES ($1, $2, $3, $4)            """,
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
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb)            """,
            record.attempt_id,
            record.work_item_id,
            record.attempt_number,
            record.lease_token,
            record.worker_ref,
            _jsonb(record.schedule_payload),
            _jsonb(record.llm_allocation_payload),
            _jsonb(record.dispatch_payload),
        )


def _jsonb(payload: Mapping[str, object]) -> str:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
