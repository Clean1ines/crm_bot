from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.workflow_runtime.application.ports.timeline_repository_port import (
    TimelineRepositoryPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)


class PostgresTimelineRepository(TimelineRepositoryPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def append_entry(
        self,
        entry: WorkflowTimelineEntry,
    ) -> WorkflowTimelineEntry:
        row = await self._connection.fetchrow(
            """
            INSERT INTO workflow_runtime_timeline_entries (
                timeline_entry_id,
                workflow_run_id,
                event_type,
                phase,
                severity,
                message,
                payload_summary,
                occurred_at,
                source_ref,
                work_item_id,
                attempt_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11)
            RETURNING
                timeline_entry_id,
                workflow_run_id,
                event_type,
                phase,
                severity,
                message,
                payload_summary,
                occurred_at,
                source_ref,
                work_item_id,
                attempt_id
            """,
            entry.timeline_entry_id,
            entry.workflow_run_id,
            entry.event_type,
            entry.phase,
            entry.severity.value,
            entry.message,
            json.dumps(dict(entry.payload_summary), default=str, sort_keys=True),
            entry.occurred_at,
            entry.source_ref,
            entry.work_item_id,
            entry.attempt_id,
        )
        if row is None:
            raise RuntimeError("timeline insert did not return row")
        return _hydrate_entry(row)

    async def list_recent_entries(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowTimelineEntry, ...]:
        if not workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty")
        if limit <= 0:
            raise ValueError("limit must be > 0")
        rows = await self._connection.fetch(
            """
            SELECT
                timeline_entry_id,
                workflow_run_id,
                event_type,
                phase,
                severity,
                message,
                payload_summary,
                occurred_at,
                source_ref,
                work_item_id,
                attempt_id
            FROM workflow_runtime_timeline_entries
            WHERE workflow_run_id = $1
            ORDER BY occurred_at DESC
            LIMIT $2
            """,
            workflow_run_id,
            limit,
        )
        return tuple(_hydrate_entry(row) for row in rows)


def _hydrate_entry(row: Mapping[str, object]) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=_required_str(row, "timeline_entry_id"),
        workflow_run_id=_required_str(row, "workflow_run_id"),
        event_type=_required_str(row, "event_type"),
        phase=_required_str(row, "phase"),
        severity=WorkflowTimelineSeverity(_required_str(row, "severity")),
        message=_required_str(row, "message"),
        payload_summary=_required_payload(row, "payload_summary"),
        occurred_at=_required_datetime(row, "occurred_at"),
        source_ref=_optional_str(row, "source_ref"),
        work_item_id=_optional_str(row, "work_item_id"),
        attempt_id=_optional_str(row, "attempt_id"),
    )


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


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value
