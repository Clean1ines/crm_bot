from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event_cursor import (
    FrontendWorkflowEventCursor,
)
from src.contexts.knowledge_workbench.observability.application.ports.frontend_workflow_event_repository_port import (
    FrontendWorkflowEventRepositoryPort,
)


class PostgresFrontendWorkflowEventRepository(FrontendWorkflowEventRepositoryPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def append(self, event: FrontendWorkflowEvent) -> FrontendWorkflowEvent:
        row = await self._connection.fetchrow(
            """
            INSERT INTO frontend_workflow_events (
                projection_event_id,
                source_event_id,
                source_sequence_number,
                projection_version,
                projection_type,
                event_type,
                operation_key,
                canonical_phase,
                workflow_run_id,
                project_id,
                document_id,
                payload,
                occurred_at,
                causation_command_id,
                correlation_id,
                projected_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12::jsonb, $13, $14, $15, $16
            )
            ON CONFLICT DO NOTHING
            RETURNING
                projection_event_id,
                source_event_id,
                source_sequence_number,
                projection_version,
                projection_type,
                event_type,
                operation_key,
                canonical_phase,
                workflow_run_id,
                project_id,
                document_id,
                payload,
                occurred_at,
                causation_command_id,
                correlation_id,
                projected_at
            """,
            event.projection_event_id,
            event.source_event_id,
            event.source_sequence_number,
            event.projection_version,
            event.projection_type,
            event.event_type,
            event.operation_key,
            event.canonical_phase,
            event.workflow_run_id,
            event.project_id,
            event.document_id,
            _json_payload(event.payload),
            event.occurred_at,
            event.causation_command_id,
            event.correlation_id,
            event.projected_at,
        )
        if row is not None:
            return _hydrate_event(row)

        existing = await self._load_by_identity(event)
        if existing is None:
            raise RuntimeError(
                "projection_event_id conflict did not return existing event"
            )
        _assert_idempotent_projection_is_same(event, existing)
        return existing

    async def list_frontend_events(
        self,
        workflow_run_id: str,
        after_cursor: FrontendWorkflowEventCursor,
        limit: int,
    ) -> tuple[FrontendWorkflowEvent, ...]:
        if not isinstance(workflow_run_id, str) or not workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty")
        if not isinstance(after_cursor, FrontendWorkflowEventCursor):
            raise TypeError("after_cursor must be FrontendWorkflowEventCursor")
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > 200
        ):
            raise ValueError("limit must be between 1 and 200")

        if after_cursor.sequence_only:
            rows = await self._connection.fetch(
                """
                SELECT
                    projection_event_id,
                    source_event_id,
                    source_sequence_number,
                    projection_version,
                    projection_type,
                    event_type,
                    operation_key,
                    canonical_phase,
                    workflow_run_id,
                    project_id,
                    document_id,
                    payload,
                    occurred_at,
                    causation_command_id,
                    correlation_id,
                    projected_at
                FROM frontend_workflow_events
                WHERE workflow_run_id = $1
                  AND source_sequence_number > $2
                ORDER BY
                    source_sequence_number ASC,
                    projection_type ASC,
                    projection_version ASC,
                    projection_event_id ASC
                LIMIT $3
                """,
                workflow_run_id,
                after_cursor.source_sequence_number,
                limit,
            )
        else:
            rows = await self._connection.fetch(
                """
                SELECT
                    projection_event_id,
                    source_event_id,
                    source_sequence_number,
                    projection_version,
                    projection_type,
                    event_type,
                    operation_key,
                    canonical_phase,
                    workflow_run_id,
                    project_id,
                    document_id,
                    payload,
                    occurred_at,
                    causation_command_id,
                    correlation_id,
                    projected_at
                FROM frontend_workflow_events
                WHERE workflow_run_id = $1
                  AND (
                      source_sequence_number,
                      projection_type,
                      projection_version,
                      projection_event_id
                  ) > (
                      $2,
                      $3,
                      $4,
                      $5
                  )
                ORDER BY
                    source_sequence_number ASC,
                    projection_type ASC,
                    projection_version ASC,
                    projection_event_id ASC
                LIMIT $6
                """,
                workflow_run_id,
                after_cursor.source_sequence_number,
                after_cursor.projection_type,
                after_cursor.projection_version,
                after_cursor.projection_event_id,
                limit,
            )
        return tuple(_hydrate_event(row) for row in rows)

    async def _load_by_identity(
        self,
        event: FrontendWorkflowEvent,
    ) -> FrontendWorkflowEvent | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                projection_event_id,
                source_event_id,
                source_sequence_number,
                projection_version,
                projection_type,
                event_type,
                operation_key,
                canonical_phase,
                workflow_run_id,
                project_id,
                document_id,
                payload,
                occurred_at,
                causation_command_id,
                correlation_id,
                projected_at
            FROM frontend_workflow_events
            WHERE projection_event_id = $1
               OR (
                    source_event_id = $2
                AND projection_type = $3
                AND projection_version = $4
               )
            """,
            event.projection_event_id,
            event.source_event_id,
            event.projection_type,
            event.projection_version,
        )
        if row is None:
            return None
        return _hydrate_event(row)


def _assert_idempotent_projection_is_same(
    expected: FrontendWorkflowEvent,
    existing: FrontendWorkflowEvent,
) -> None:
    comparable_fields = (
        "projection_event_id",
        "source_event_id",
        "source_sequence_number",
        "projection_version",
        "projection_type",
        "event_type",
        "operation_key",
        "canonical_phase",
        "workflow_run_id",
        "project_id",
        "document_id",
        "occurred_at",
        "causation_command_id",
        "correlation_id",
        "projected_at",
    )
    for field_name in comparable_fields:
        if getattr(expected, field_name) != getattr(existing, field_name):
            raise ValueError(f"projection_event_id conflict has different {field_name}")
    if dict(expected.payload) != dict(existing.payload):
        raise ValueError("projection_event_id conflict has different payload")


def _hydrate_event(row: Mapping[str, object]) -> FrontendWorkflowEvent:
    return FrontendWorkflowEvent(
        projection_event_id=_required_str(row, "projection_event_id"),
        source_event_id=_required_str(row, "source_event_id"),
        source_sequence_number=_required_int(row, "source_sequence_number"),
        projection_version=_required_int(row, "projection_version"),
        projection_type=_required_str(row, "projection_type"),
        event_type=_required_str(row, "event_type"),
        operation_key=_optional_str(row, "operation_key"),
        canonical_phase=_required_str(row, "canonical_phase"),
        workflow_run_id=_required_str(row, "workflow_run_id"),
        project_id=_required_str(row, "project_id"),
        document_id=_required_str(row, "document_id"),
        payload=_required_payload(row, "payload"),
        occurred_at=_required_datetime(row, "occurred_at"),
        causation_command_id=_optional_str(row, "causation_command_id"),
        correlation_id=_optional_str(row, "correlation_id"),
        projected_at=_required_datetime(row, "projected_at"),
    )


def _json_payload(payload: Mapping[str, object]) -> str:
    return json.dumps(
        dict(payload),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
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


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be int")
    return value


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value
