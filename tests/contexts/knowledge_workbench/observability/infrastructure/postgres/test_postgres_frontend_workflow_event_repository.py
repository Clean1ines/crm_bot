from __future__ import annotations

import json
import math
import inspect
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event_cursor import (
    FrontendWorkflowEventCursor,
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

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> list[Mapping[str, object]]:
        if "FROM frontend_workflow_events" not in query:
            raise AssertionError(query)
        workflow_run_id = _arg_str(args, 0)
        limit = _arg_int(args, -1)
        if "source_sequence_number > $2" in query:
            after_source_sequence = _arg_int(args, 1)
            rows = (
                row
                for row in self.rows.values()
                if row["workflow_run_id"] == workflow_run_id
                and _row_int(row, "source_sequence_number") > after_source_sequence
            )
        else:
            after_cursor = FrontendWorkflowEventCursor(
                source_sequence_number=_arg_int(args, 1),
                projection_type=_arg_str(args, 2),
                projection_version=_arg_int(args, 3),
                projection_event_id=_arg_str(args, 4),
            )
            rows = (
                row
                for row in self.rows.values()
                if row["workflow_run_id"] == workflow_run_id
                and _row_is_after_cursor(row, after_cursor)
            )
        return sorted(
            rows,
            key=lambda row: (
                _row_int(row, "source_sequence_number"),
                _row_str(row, "projection_type"),
                _row_int(row, "projection_version"),
                _row_str(row, "projection_event_id"),
            ),
        )[:limit]


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


def _row_str(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError("expected string row value")
    return value


def _row_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("expected int row value")
    return value


def _row_is_after_cursor(
    row: Mapping[str, object],
    after_cursor: FrontendWorkflowEventCursor,
) -> bool:
    return (
        _row_int(row, "source_sequence_number"),
        _row_str(row, "projection_type"),
        _row_int(row, "projection_version"),
        _row_str(row, "projection_event_id"),
    ) > (
        after_cursor.source_sequence_number,
        after_cursor.projection_type,
        after_cursor.projection_version,
        after_cursor.projection_event_id,
    )


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


@pytest.mark.asyncio
async def test_list_frontend_events_uses_deterministic_composite_order() -> None:
    connection = FakeConnection()
    connection.rows = {
        event.projection_event_id: _event_row(event)
        for event in (
            _event_with_order(sequence=12, projection_type="z", version=1, suffix="c"),
            _event_with_order(sequence=11, projection_type="z", version=1, suffix="b"),
            _event_with_order(sequence=11, projection_type="a", version=2, suffix="d"),
            _event_with_order(sequence=11, projection_type="a", version=1, suffix="a"),
        )
    }
    repository = PostgresFrontendWorkflowEventRepository(
        cast(asyncpg.Connection, connection)
    )

    events = await repository.list_frontend_events(
        "workflow-1",
        FrontendWorkflowEventCursor.beginning(),
        limit=10,
    )

    assert tuple(event.projection_event_id for event in events) == (
        "projection-a",
        "projection-d",
        "projection-b",
        "projection-c",
    )


@pytest.mark.asyncio
async def test_list_frontend_events_applies_after_source_sequence_and_limit() -> None:
    connection = FakeConnection()
    connection.rows = {
        event.projection_event_id: _event_row(event)
        for event in (
            _event_with_order(sequence=10, projection_type="a", version=1, suffix="a"),
            _event_with_order(sequence=11, projection_type="a", version=1, suffix="b"),
            _event_with_order(sequence=12, projection_type="a", version=1, suffix="c"),
        )
    }
    repository = PostgresFrontendWorkflowEventRepository(
        cast(asyncpg.Connection, connection)
    )

    events = await repository.list_frontend_events(
        "workflow-1",
        FrontendWorkflowEventCursor.from_legacy_source_sequence(10),
        limit=1,
    )

    assert tuple(event.source_sequence_number for event in events) == (11,)


def test_list_frontend_events_reads_only_projection_table() -> None:
    source = inspect.getsource(
        PostgresFrontendWorkflowEventRepository.list_frontend_events
    )

    assert "FROM frontend_workflow_events" in source
    for forbidden_table in (
        "execution_",
        "capacity_",
        "workflow_runtime_",
        "knowledge_extraction_",
    ):
        assert forbidden_table not in source


@pytest.mark.asyncio
async def test_list_frontend_events_composite_cursor_continues_same_sequence() -> None:
    connection = FakeConnection()
    first = _event_with_order(sequence=11, projection_type="a", version=1, suffix="a")
    second = _event_with_order(sequence=11, projection_type="b", version=1, suffix="b")
    connection.rows = {
        event.projection_event_id: _event_row(event) for event in (first, second)
    }
    repository = PostgresFrontendWorkflowEventRepository(
        cast(asyncpg.Connection, connection)
    )

    events = await repository.list_frontend_events(
        "workflow-1",
        FrontendWorkflowEventCursor.from_event(first),
        limit=10,
    )

    assert tuple(event.projection_event_id for event in events) == ("projection-b",)


@pytest.mark.asyncio
async def test_list_frontend_events_pages_250_events_within_one_sequence() -> None:
    connection = FakeConnection()
    events = tuple(
        _event_with_order(
            sequence=42,
            projection_type="workflow_source_units_created",
            version=1,
            suffix=f"{index:03d}",
        )
        for index in range(250)
    )
    connection.rows = {event.projection_event_id: _event_row(event) for event in events}
    repository = PostgresFrontendWorkflowEventRepository(
        cast(asyncpg.Connection, connection)
    )

    first_page = await repository.list_frontend_events(
        "workflow-1",
        FrontendWorkflowEventCursor.beginning(),
        limit=200,
    )
    second_page = await repository.list_frontend_events(
        "workflow-1",
        FrontendWorkflowEventCursor.from_event(first_page[-1]),
        limit=200,
    )

    assert len(first_page) == 200
    assert len(second_page) == 50
    assert first_page[-1].projection_event_id == "projection-199"
    assert second_page[0].projection_event_id == "projection-200"


def _event_with_order(
    *,
    sequence: int,
    projection_type: str,
    version: int,
    suffix: str,
) -> FrontendWorkflowEvent:
    return FrontendWorkflowEvent(
        projection_event_id=f"projection-{suffix}",
        source_event_id=f"source-{suffix}",
        source_sequence_number=sequence,
        projection_version=version,
        projection_type=projection_type,
        event_type="SourceUnitsCreated",
        operation_key="ingest_source_document",
        canonical_phase="SOURCE_INGESTION",
        workflow_run_id="workflow-1",
        project_id="project-1",
        document_id="document-1",
        payload={"source_unit_count": 3},
        occurred_at=_now(),
        projected_at=_now(),
    )


def _event_row(event: FrontendWorkflowEvent) -> dict[str, object]:
    return {
        "projection_event_id": event.projection_event_id,
        "source_event_id": event.source_event_id,
        "source_sequence_number": event.source_sequence_number,
        "projection_version": event.projection_version,
        "projection_type": event.projection_type,
        "event_type": event.event_type,
        "operation_key": event.operation_key,
        "canonical_phase": event.canonical_phase,
        "workflow_run_id": event.workflow_run_id,
        "project_id": event.project_id,
        "document_id": event.document_id,
        "payload": dict(event.payload),
        "occurred_at": event.occurred_at,
        "causation_command_id": event.causation_command_id,
        "correlation_id": event.correlation_id,
        "projected_at": event.projected_at,
    }
