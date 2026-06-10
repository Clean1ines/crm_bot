from __future__ import annotations

from datetime import datetime
import json
from collections.abc import Mapping

import asyncpg

from src.contexts.execution_runtime.application.ports.work_item_scheduling_unit_of_work_port import (
    WorkItemSchedulingUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


class UnitOfWorkClosedError(RuntimeError):
    """Raised when a closed scheduling Unit of Work is used again."""


class PostgresWorkItemSchedulingUnitOfWork(WorkItemSchedulingUnitOfWorkPort):
    """Asyncpg scheduling UoW for generic Execution Runtime work items.

    The UoW owns a transaction lazily when the first write happens. Pure read
    idempotency checks may complete without opening a transaction; in that case
    commit/rollback only close the UoW.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection
        self._transaction: asyncpg.transaction.Transaction | None = None
        self._closed = False

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        self._ensure_not_closed()
        row = await self._connection.fetchrow(
            """
            SELECT
                work_item_id,
                work_kind,
                status,
                attempt_count,
                leased_by,
                lease_token,
                lease_expires_at,
                next_attempt_at,
                last_error_kind
            FROM execution_work_items
            WHERE work_item_id = $1
            """,
            work_item_id,
        )
        if row is None:
            return None
        return _hydrate_work_item(row)

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        self._ensure_not_closed()
        value = await self._connection.fetchval(
            """
            SELECT payload_hash
            FROM execution_work_item_schedules
            WHERE work_item_id = $1
            """,
            work_item_id,
        )
        if value is None:
            return None
        return str(value)

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: Mapping[str, object],
    ) -> None:
        await self._ensure_open_transaction()
        await self._connection.execute(
            """
            INSERT INTO execution_work_items (
                work_item_id,
                work_kind,
                status,
                attempt_count,
                leased_by,
                lease_token,
                lease_expires_at,
                next_attempt_at,
                last_error_kind
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (work_item_id) DO NOTHING
            """,
            item.work_item_id,
            item.work_kind.value,
            item.status.value,
            item.attempt_count,
            item.leased_by.value if item.leased_by is not None else None,
            item.lease_token.value if item.lease_token is not None else None,
            item.lease_expires_at,
            item.next_attempt_at.value if item.next_attempt_at is not None else None,
            item.last_error_kind,
        )
        await self._connection.execute(
            """
            INSERT INTO execution_work_item_schedules (
                work_item_id,
                idempotency_key,
                payload_hash,
                payload
            )
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (work_item_id) DO NOTHING
            """,
            item.work_item_id,
            idempotency_key,
            payload_hash,
            json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True),
        )

    async def commit(self) -> None:
        self._ensure_not_closed()
        if self._transaction is None:
            self._closed = True
            return

        try:
            await self._transaction.commit()
        except Exception:
            await self._transaction.rollback()
            self._closed = True
            raise

        self._closed = True

    async def rollback(self) -> None:
        self._ensure_not_closed()
        if self._transaction is not None:
            await self._transaction.rollback()
        self._closed = True

    async def _ensure_open_transaction(self) -> None:
        self._ensure_not_closed()
        if self._transaction is None:
            self._transaction = self._connection.transaction()
            await self._transaction.start()

    def _ensure_not_closed(self) -> None:
        if self._closed:
            raise UnitOfWorkClosedError(
                "Work item scheduling UnitOfWork is already closed"
            )


def _hydrate_work_item(row: Mapping[str, object]) -> WorkItem:
    attempt_count = row["attempt_count"]
    if not isinstance(attempt_count, int):
        raise TypeError("attempt_count must be int")

    lease_expires_at = row["lease_expires_at"]
    if lease_expires_at is not None and not isinstance(lease_expires_at, datetime):
        raise TypeError("lease_expires_at must be datetime or None")

    next_attempt_at = row["next_attempt_at"]
    if next_attempt_at is not None and not isinstance(next_attempt_at, datetime):
        raise TypeError("next_attempt_at must be datetime or None")

    leased_by = row["leased_by"]
    lease_token = row["lease_token"]
    last_error_kind = row["last_error_kind"]

    return WorkItem(
        work_item_id=str(row["work_item_id"]),
        work_kind=WorkKind(str(row["work_kind"])),
        status=WorkItemStatus(str(row["status"])),
        attempt_count=attempt_count,
        leased_by=WorkerRef(str(leased_by)) if leased_by is not None else None,
        lease_token=LeaseToken(str(lease_token)) if lease_token is not None else None,
        lease_expires_at=lease_expires_at,
        next_attempt_at=WaitUntil(next_attempt_at)
        if next_attempt_at is not None
        else None,
        last_error_kind=str(last_error_kind) if last_error_kind is not None else None,
    )
