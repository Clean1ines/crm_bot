from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress import (
    ClaimExtractionStageProgressQueryPort,
)


class AsyncStageProgressConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[object]: ...

    async def fetchval(self, query: str, *args: object) -> object: ...


@dataclass(frozen=True, slots=True)
class ExecutionWorkItemRow:
    work_item_id: str
    work_kind: str
    status: str
    attempt_count: int
    leased_by: str | None
    lease_token: str | None
    lease_expires_at: datetime | None
    next_attempt_at: datetime | None
    last_error_kind: str | None


class PostgresClaimExtractionStageProgressQuery(ClaimExtractionStageProgressQueryPort):
    """PostgreSQL query adapter for claim-extraction stage progress.

    It reads generic Execution Runtime work items through a narrow stage index.
    It does not depend on legacy Workbench observability tables or HTTP/frontend code.
    """

    def __init__(self, connection: AsyncStageProgressConnectionLike) -> None:
        self._connection = connection

    async def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]:
        rows = await self._connection.fetch(
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
                wi.last_error_kind
            FROM claim_extraction_stage_work_items AS stage_items
            JOIN execution_work_items AS wi
                ON wi.work_item_id = stage_items.work_item_id
            WHERE stage_items.workflow_run_id = $1
              AND stage_items.stage_run_id = $2
            ORDER BY stage_items.created_at ASC, wi.work_item_id ASC
            """,
            workflow_run_id,
            stage_run_id,
        )
        return tuple(_row_to_work_item(row) for row in rows)

    async def count_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> int:
        value = await self._connection.fetchval(
            """
            SELECT count(*)
            FROM pipeline_artifacts
            WHERE payload ->> 'workflow_run_id' = $1
              AND payload ->> 'stage_run_id' = $2
              AND artifact_kind LIKE 'knowledge_workbench.claim_observations.%'
              AND status NOT IN ('rejected', 'expired')
            """,
            workflow_run_id,
            stage_run_id,
        )
        if not isinstance(value, int):
            raise TypeError("claim extraction artifact count query must return int")
        return value


def _row_to_work_item(row: object) -> WorkItem:
    item_row = _execution_work_item_row(row)
    return WorkItem(
        work_item_id=item_row.work_item_id,
        work_kind=WorkKind(item_row.work_kind),
        status=WorkItemStatus(item_row.status),
        attempt_count=item_row.attempt_count,
        leased_by=WorkerRef(item_row.leased_by) if item_row.leased_by else None,
        lease_token=LeaseToken(item_row.lease_token) if item_row.lease_token else None,
        lease_expires_at=item_row.lease_expires_at,
        next_attempt_at=WaitUntil(item_row.next_attempt_at)
        if item_row.next_attempt_at
        else None,
        last_error_kind=item_row.last_error_kind,
    )


def _execution_work_item_row(row: object) -> ExecutionWorkItemRow:
    return ExecutionWorkItemRow(
        work_item_id=_required_str(row, "work_item_id"),
        work_kind=_required_str(row, "work_kind"),
        status=_required_str(row, "status"),
        attempt_count=_required_int(row, "attempt_count"),
        leased_by=_optional_str(row, "leased_by"),
        lease_token=_optional_str(row, "lease_token"),
        lease_expires_at=_optional_datetime(row, "lease_expires_at"),
        next_attempt_at=_optional_datetime(row, "next_attempt_at"),
        last_error_kind=_optional_str(row, "last_error_kind"),
    )


def _value(row: object, key: str) -> object:
    try:
        return row[key]  # type: ignore[index]
    except KeyError as exc:
        raise KeyError(f"Missing execution_work_items column: {key}") from exc


def _required_str(row: object, key: str) -> str:
    value = _value(row, key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _optional_str(row: object, key: str) -> str | None:
    value = _value(row, key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be null or a non-empty string")
    return value


def _required_int(row: object, key: str) -> int:
    value = _value(row, key)
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _optional_datetime(row: object, key: str) -> datetime | None:
    value = _value(row, key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime or null")
    return value
