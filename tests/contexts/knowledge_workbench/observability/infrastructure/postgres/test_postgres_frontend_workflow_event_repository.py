from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.infrastructure.postgres.postgres_frontend_workflow_event_repository import (
    PostgresFrontendWorkflowEventRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _event(
    *,
    projection_event_id: str = (
        "frontend-workflow-event:source-event-1:workflow_source_units_created:v1"
    ),
    payload: Mapping[str, object] | None = None,
) -> FrontendWorkflowEvent:
    return FrontendWorkflowEvent(
        projection_event_id=projection_event_id,
        source_event_id="source-event-1",
        source_sequence_number=17,
        projection_version=1,
        projection_type="workflow_source_units_created",
        event_type="SourceUnitsCreated",
        operation_key="ingest_source_document",
        canonical_phase="SOURCE_INGESTION",
        workflow_run_id="workflow-1",
        project_id="project-1",
        document_id="document-1",
        payload={"source_unit_count": 3} if payload is None else payload,
        occurred_at=_now(),
        projected_at=_now(),
    )


class FakeConnection:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "INSERT INTO frontend_workflow_events" in query:
            projection_event_id = _arg_str(args, 0)
            natural_key = (_arg_str(args, 1), _arg_str(args, 4), _arg_int(args, 3))
            if projection_event_id in self.rows or any(
                (
                    row["source_event_id"],
                    row["projection_type"],
                    row["projection_version"],
                )
                == natural_key
                for row in self.rows.values()
            ):
                return None
            row = {
                "projection_event_id": args[0],
                "source_event_id": args[1],
                "source_sequence_number": args[2],
                "projection_version": args[3],
                "projection_type": args[4],
                "event_type": args[5],
                "operation_key": args[6],
                "canonical_phase": args[7],
                "workflow_run_id": args[8],
                "project_id": args[9],
                "document_id": args[10],
                "payload": json.loads(_arg_str(args, 11)),
                "occurred_at": args[12],
                "causation_command_id": args[13],
                "correlation_id": args[14],
                "projected_at": args[15],
            }
            self.rows[projection_event_id] = row
            return row

        if "WHERE projection_event_id = $1" in query:
            projection_event_id = _arg_str(args, 0)
            natural_key = (_arg_str(args, 1), _arg_str(args, 2), _arg_int(args, 3))
            by_id = self.rows.get(projection_event_id)
            if by_id is not None:
                return by_id
            return next(
                (
                    row
                    for row in self.rows.values()
                    if (
                        row["source_event_id"],
                        row["projection_type"],
                        row["projection_version"],
                    )
                    == natural_key
                ),
                None,
            )

        raise AssertionError(query)


def _arg_str(args: tuple[object, ...], index: int) -> str:
    value = args[index]
    if not isinstance(value, str):
        raise TypeError("expected string argument")
    return value


def _arg_int(args: tuple[object, ...], index: int) -> int:
    value = args[index]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("expected int argument")
    return value


@pytest.mark.asyncio
async def test_append_is_idempotent_for_same_projection_event() -> None:
    connection = FakeConnection()
    repository = PostgresFrontendWorkflowEventRepository(
        cast(asyncpg.Connection, connection)
    )

    first = await repository.append(_event())
    second = await repository.append(_event())

    assert first == second
    assert tuple(connection.rows) == (
        "frontend-workflow-event:source-event-1:workflow_source_units_created:v1",
    )


@pytest.mark.asyncio
async def test_append_rejects_idempotency_key_payload_mismatch() -> None:
    connection = FakeConnection()
    repository = PostgresFrontendWorkflowEventRepository(
        cast(asyncpg.Connection, connection)
    )

    await repository.append(_event())

    with pytest.raises(ValueError, match="different payload"):
        await repository.append(_event(payload={"source_unit_count": 4}))


@pytest.mark.asyncio
async def test_append_rejects_natural_key_with_different_projection_event_id() -> None:
    connection = FakeConnection()
    repository = PostgresFrontendWorkflowEventRepository(
        cast(asyncpg.Connection, connection)
    )

    await repository.append(_event())

    with pytest.raises(ValueError, match="different projection_event_id"):
        await repository.append(
            _event(projection_event_id="frontend-workflow-event:different")
        )


@pytest.mark.asyncio
async def test_append_rejects_non_finite_payload_before_database_write() -> None:
    connection = FakeConnection()
    repository = PostgresFrontendWorkflowEventRepository(
        cast(asyncpg.Connection, connection)
    )

    with pytest.raises(ValueError, match="Out of range float values"):
        await repository.append(_event(payload={"source_unit_count": math.nan}))

    assert connection.rows == {}
