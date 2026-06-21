from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event_cursor import (
    FrontendWorkflowEventCursor,
)


def _event(
    *,
    projection_event_id: str = "projection-1",
    source_sequence_number: int = 17,
    projection_type: str = "workflow_source_units_created",
    projection_version: int = 1,
) -> FrontendWorkflowEvent:
    occurred_at = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    return FrontendWorkflowEvent(
        projection_event_id=projection_event_id,
        source_event_id="source-event-1",
        source_sequence_number=source_sequence_number,
        projection_version=projection_version,
        projection_type=projection_type,
        event_type="SourceUnitsCreated",
        operation_key="ingest_source_document",
        canonical_phase="SOURCE_INGESTION",
        workflow_run_id="workflow-1",
        project_id="project-1",
        document_id="document-1",
        payload={"source_unit_count": 3},
        occurred_at=occurred_at,
        projected_at=occurred_at,
    )


def test_cursor_round_trip_serialize_and_parse() -> None:
    cursor = FrontendWorkflowEventCursor(
        source_sequence_number=42,
        projection_type="workflow_source_units_created",
        projection_version=2,
        projection_event_id="projection-abc",
    )

    parsed = FrontendWorkflowEventCursor.parse(cursor.serialize())

    assert parsed == cursor


def test_cursor_from_event() -> None:
    event = _event(
        projection_event_id="projection-xyz",
        source_sequence_number=99,
        projection_type="type-b",
        projection_version=3,
    )

    cursor = FrontendWorkflowEventCursor.from_event(event)

    assert cursor.source_sequence_number == 99
    assert cursor.projection_type == "type-b"
    assert cursor.projection_version == 3
    assert cursor.projection_event_id == "projection-xyz"
    assert cursor.sequence_only is False


def test_legacy_source_sequence_cursor_is_sequence_only() -> None:
    cursor = FrontendWorkflowEventCursor.from_legacy_source_sequence(10)

    assert cursor.source_sequence_number == 10
    assert cursor.sequence_only is True


def test_sequence_only_cursor_cannot_be_serialized() -> None:
    cursor = FrontendWorkflowEventCursor.from_legacy_source_sequence(10)

    with pytest.raises(ValueError, match="sequence-only"):
        cursor.serialize()


@pytest.mark.parametrize(
    "invalid_cursor",
    (
        "",
        "   ",
        "not-base64!!!",
        "e30=",  # {}
    ),
)
def test_parse_rejects_invalid_cursor(invalid_cursor: str) -> None:
    with pytest.raises(ValueError):
        FrontendWorkflowEventCursor.parse(invalid_cursor)
