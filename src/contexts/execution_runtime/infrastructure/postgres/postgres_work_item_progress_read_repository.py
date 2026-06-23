from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
    WorkItemProgressSummary,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind


class PostgresWorkItemProgressReadRepository(WorkItemProgressReadRepositoryPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def summarize_by_work_kind_and_workflow(
        self,
        *,
        workflow_run_id: str,
        work_kind: WorkKind,
        now: datetime,
    ) -> WorkItemProgressSummary:
        if not workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")

        row = await self._connection.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE wi.status = 'ready') AS ready_count,
                COUNT(*) FILTER (WHERE wi.status = 'leased') AS leased_count,
                0 AS deferred_count,
                COUNT(*) FILTER (WHERE wi.status = 'retryable_failed') AS retryable_failed_count,
                COUNT(*) FILTER (WHERE wi.status = 'completed') AS completed_count,
                COUNT(*) FILTER (WHERE wi.status = 'terminal_failed') AS terminal_failed_count,
                COUNT(*) FILTER (WHERE wi.status = 'cancelled') AS cancelled_count,
                COUNT(*) FILTER (WHERE wi.status = 'split_superseded') AS split_superseded_count,
                COUNT(*) FILTER (WHERE wi.status = 'user_action_required') AS user_action_required_count,
                COUNT(*) AS total_count,
                NULL::timestamptz AS next_due_at,
                0 AS due_deferred_count,
                COUNT(*) FILTER (WHERE wi.status = 'retryable_failed') AS due_retryable_failed_count
            FROM execution_work_items wi
            JOIN execution_work_item_schedules wis
              ON wis.work_item_id = wi.work_item_id
            WHERE wi.work_kind = $1
              AND wis.payload->>'workflow_run_id' = $2
            """,
            work_kind.value,
            workflow_run_id,
        )
        if row is None:
            return WorkItemProgressSummary(
                ready_count=0,
                leased_count=0,
                deferred_count=0,
                retryable_failed_count=0,
                completed_count=0,
                terminal_failed_count=0,
                cancelled_count=0,
                split_superseded_count=0,
                user_action_required_count=0,
                total_count=0,
                next_due_at=None,
            )

        return _summary_from_row(row)


def _summary_from_row(row: Mapping[str, object]) -> WorkItemProgressSummary:
    return WorkItemProgressSummary(
        ready_count=_row_int(row, "ready_count"),
        leased_count=_row_int(row, "leased_count"),
        deferred_count=_row_int(row, "deferred_count"),
        retryable_failed_count=_row_int(row, "retryable_failed_count"),
        completed_count=_row_int(row, "completed_count"),
        terminal_failed_count=_row_int(row, "terminal_failed_count"),
        cancelled_count=_row_int(row, "cancelled_count"),
        split_superseded_count=_row_int(row, "split_superseded_count"),
        user_action_required_count=_row_int(row, "user_action_required_count"),
        total_count=_row_int(row, "total_count"),
        next_due_at=None,
        due_deferred_count=_row_int(row, "due_deferred_count"),
        due_retryable_failed_count=_row_int(row, "due_retryable_failed_count"),
    )


def _row_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value
