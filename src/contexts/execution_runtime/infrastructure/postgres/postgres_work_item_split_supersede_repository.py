from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.execution_runtime.application.ports.work_item_split_supersede_repository_port import (
    WorkItemSplitSupersedeRepositoryPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


class PostgresWorkItemSplitSupersedeRepository(
    WorkItemSplitSupersedeRepositoryPort,
):
    """Postgres adapter for split-superseding existing Execution Runtime work items.

    Transaction lifecycle is owned by the application composition boundary.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def load_work_item(self, work_item_id: str) -> WorkItem | None:
        _require_non_empty_text(work_item_id, field_name="work_item_id")
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

    async def save_work_item(self, item: WorkItem) -> None:
        if not isinstance(item, WorkItem):
            raise TypeError("item must be WorkItem")
        await self._connection.execute(
            """
            UPDATE execution_work_items
            SET
                status = $2,
                attempt_count = $3,
                leased_by = $4,
                lease_token = $5,
                lease_expires_at = $6,
                next_attempt_at = $7,
                last_error_kind = $8,
                updated_at = NOW()
            WHERE work_item_id = $1
            """,
            item.work_item_id,
            item.status.value,
            item.attempt_count,
            item.leased_by.value if item.leased_by is not None else None,
            item.lease_token.value if item.lease_token is not None else None,
            item.lease_expires_at,
            item.next_attempt_at.value if item.next_attempt_at is not None else None,
            item.last_error_kind,
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


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
