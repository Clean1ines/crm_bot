from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


class PostgresWorkItemLeaseRepository(WorkItemLeaseRepositoryPort):
    """Asyncpg repository for atomically leasing due Execution Runtime work items.

    Transaction lifecycle is owned by the composing application boundary. This
    repository only uses the provided connection.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def lease_due_work_item(
        self,
        *,
        work_kind: WorkKind,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                wi.work_item_id,
                wi.work_kind,
                wi.status,
                wi.attempt_count,
                wi.leased_by,
                wi.lease_token,
                wi.lease_expires_at,
                wi.next_attempt_at,
                wi.last_error_kind,
                wi.created_at,
                wi.updated_at,
                wis.payload
            FROM execution_work_items wi
            JOIN execution_work_item_schedules wis
              ON wis.work_item_id = wi.work_item_id
            WHERE wi.work_kind = $1
              AND wi.status IN ('ready', 'deferred', 'retryable_failed')
              AND (wi.next_attempt_at IS NULL OR wi.next_attempt_at <= $2)
            ORDER BY
              wi.next_attempt_at NULLS FIRST,
              wi.updated_at,
              wi.work_item_id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """,
            work_kind.value,
            now,
        )
        if row is None:
            return None

        item = _hydrate_work_item(row)
        payload = _hydrate_schedule_payload(row["payload"])
        leased_item = WorkItemStateMachine.lease_ready(
            item,
            worker=worker,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            now=now,
        )

        await self._connection.execute(
            """
            UPDATE execution_work_items
            SET
                status = $2,
                attempt_count = $3,
                leased_by = $4,
                lease_token = $5,
                lease_expires_at = $6,
                next_attempt_at = NULL,
                last_error_kind = NULL,
                updated_at = $7
            WHERE work_item_id = $1
            """,
            leased_item.work_item_id,
            leased_item.status.value,
            leased_item.attempt_count,
            leased_item.leased_by.value if leased_item.leased_by is not None else None,
            leased_item.lease_token.value
            if leased_item.lease_token is not None
            else None,
            leased_item.lease_expires_at,
            now,
        )

        return LeasedWorkItemRecord(
            work_item=leased_item,
            schedule_payload=payload,
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


def _hydrate_schedule_payload(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("payload must be Mapping")
    return value
