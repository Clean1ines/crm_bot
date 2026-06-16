from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.execution_runtime.infrastructure.postgres.jsonb_payload_hydration import (
    hydrate_jsonb_object_payload,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
    WorkItemAttemptDispatchReadRepositoryPort,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken


class PostgresReadWorkItemAttemptDispatchRepository(
    WorkItemAttemptDispatchReadRepositoryPort,
):
    """Reads prepared dispatch attempts for execution.

    Transaction ownership belongs to the composing application boundary.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def get_dispatch_for_execution(
        self,
        *,
        attempt_id: str,
    ) -> WorkItemAttemptDispatchForExecution | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                d.attempt_id,
                d.work_item_id,
                d.attempt_number,
                d.lease_token,
                d.worker_ref,
                d.dispatch_payload,
                a.started_at
            FROM execution_work_item_attempt_dispatches d
            JOIN execution_work_item_attempts a
              ON a.attempt_id = d.attempt_id
            WHERE d.attempt_id = $1
            """,
            attempt_id,
        )
        if row is None:
            return None

        return WorkItemAttemptDispatchForExecution(
            attempt_id=_require_text(row, "attempt_id"),
            work_item_id=_require_text(row, "work_item_id"),
            attempt_number=_require_int(row, "attempt_number"),
            lease_token=LeaseToken(_require_text(row, "lease_token")),
            worker_ref=_require_text(row, "worker_ref"),
            dispatch_payload=_require_mapping(row, "dispatch_payload"),
            started_at=_require_datetime(row, "started_at"),
        )


def _require_text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    if not value.strip():
        raise ValueError(f"{key} must be non-empty")
    return value


def _require_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _require_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value


def _require_mapping(
    row: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    return hydrate_jsonb_object_payload(
        row[key],
        field_name=f"execution_work_item_attempt_dispatches.{key}",
    )
