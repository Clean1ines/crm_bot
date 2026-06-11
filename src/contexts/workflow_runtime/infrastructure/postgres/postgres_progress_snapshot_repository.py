from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.workflow_runtime.application.ports.progress_snapshot_repository_port import (
    ProgressSnapshotRepositoryPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)


class PostgresProgressSnapshotRepository(ProgressSnapshotRepositoryPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def get_snapshot(
        self,
        workflow_run_id: str,
    ) -> WorkflowProgressSnapshot | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                workflow_run_id,
                current_phase,
                workflow_status,
                total_work_items,
                scheduled_work_items,
                running_work_items,
                completed_work_items,
                deferred_work_items,
                retryable_failed_work_items,
                terminal_failed_work_items,
                blocked_work_items,
                domain_counters,
                started_at,
                updated_at,
                completed_at
            FROM workflow_runtime_progress_snapshots
            WHERE workflow_run_id = $1
            """,
            workflow_run_id,
        )
        if row is None:
            return None
        return _hydrate_snapshot(row)

    async def save_snapshot(
        self,
        snapshot: WorkflowProgressSnapshot,
    ) -> WorkflowProgressSnapshot:
        row = await self._connection.fetchrow(
            """
            INSERT INTO workflow_runtime_progress_snapshots (
                workflow_run_id,
                current_phase,
                workflow_status,
                total_work_items,
                scheduled_work_items,
                running_work_items,
                completed_work_items,
                deferred_work_items,
                retryable_failed_work_items,
                terminal_failed_work_items,
                blocked_work_items,
                domain_counters,
                started_at,
                updated_at,
                completed_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12::jsonb, $13, $14, $15
            )
            ON CONFLICT (workflow_run_id) DO UPDATE
            SET current_phase = EXCLUDED.current_phase,
                workflow_status = EXCLUDED.workflow_status,
                total_work_items = EXCLUDED.total_work_items,
                scheduled_work_items = EXCLUDED.scheduled_work_items,
                running_work_items = EXCLUDED.running_work_items,
                completed_work_items = EXCLUDED.completed_work_items,
                deferred_work_items = EXCLUDED.deferred_work_items,
                retryable_failed_work_items = EXCLUDED.retryable_failed_work_items,
                terminal_failed_work_items = EXCLUDED.terminal_failed_work_items,
                blocked_work_items = EXCLUDED.blocked_work_items,
                domain_counters = EXCLUDED.domain_counters,
                started_at = EXCLUDED.started_at,
                updated_at = EXCLUDED.updated_at,
                completed_at = EXCLUDED.completed_at
            RETURNING
                workflow_run_id,
                current_phase,
                workflow_status,
                total_work_items,
                scheduled_work_items,
                running_work_items,
                completed_work_items,
                deferred_work_items,
                retryable_failed_work_items,
                terminal_failed_work_items,
                blocked_work_items,
                domain_counters,
                started_at,
                updated_at,
                completed_at
            """,
            snapshot.workflow_run_id,
            snapshot.current_phase,
            snapshot.workflow_status,
            snapshot.total_work_items,
            snapshot.scheduled_work_items,
            snapshot.running_work_items,
            snapshot.completed_work_items,
            snapshot.deferred_work_items,
            snapshot.retryable_failed_work_items,
            snapshot.terminal_failed_work_items,
            snapshot.blocked_work_items,
            json.dumps(dict(snapshot.domain_counters), sort_keys=True),
            snapshot.started_at,
            snapshot.updated_at,
            snapshot.completed_at,
        )
        if row is None:
            raise RuntimeError("progress snapshot upsert did not return row")
        return _hydrate_snapshot(row)


def _hydrate_snapshot(row: Mapping[str, object]) -> WorkflowProgressSnapshot:
    return WorkflowProgressSnapshot(
        workflow_run_id=_required_str(row, "workflow_run_id"),
        current_phase=_required_str(row, "current_phase"),
        workflow_status=_required_str(row, "workflow_status"),
        total_work_items=_required_int(row, "total_work_items"),
        scheduled_work_items=_required_int(row, "scheduled_work_items"),
        running_work_items=_required_int(row, "running_work_items"),
        completed_work_items=_required_int(row, "completed_work_items"),
        deferred_work_items=_required_int(row, "deferred_work_items"),
        retryable_failed_work_items=_required_int(row, "retryable_failed_work_items"),
        terminal_failed_work_items=_required_int(row, "terminal_failed_work_items"),
        blocked_work_items=_required_int(row, "blocked_work_items"),
        domain_counters=_required_int_mapping(row, "domain_counters"),
        started_at=_optional_datetime(row, "started_at"),
        updated_at=_required_datetime(row, "updated_at"),
        completed_at=_optional_datetime(row, "completed_at"),
    )


def _required_int_mapping(row: Mapping[str, object], key: str) -> Mapping[str, int]:
    value = row[key]
    if isinstance(value, str):
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise TypeError(f"{key} must decode to object")
        value = decoded
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be mapping")
    result: dict[str, int] = {}
    for nested_key, nested_value in value.items():
        if not isinstance(nested_key, str):
            raise TypeError(f"{key} key must be str")
        if not isinstance(nested_value, int):
            raise TypeError(f"{key}.{nested_key} must be int")
        result[nested_key] = nested_value
    return result


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty string")
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


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = row[key]
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime or null")
    return value
