from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import cast

import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_type: str = "SourceUnitsCreated",
    payload: dict[str, object] | None = None,
    occurred_at: datetime | None = None,
    sequence_number: int | None = 1,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId("event-1"),
        event_type=event_type,
        workflow_run_id="workflow-1",
        payload={"source_unit_count": 2} if payload is None else payload,
        occurred_at=_now() if occurred_at is None else occurred_at,
        sequence_number=sequence_number,
    )


def test_workflow_event_rejects_empty_event_type() -> None:
    with pytest.raises(ValueError, match="event_type must be non-empty"):
        _event(event_type=" ")


def test_workflow_event_freezes_payload() -> None:
    payload = {"source_unit_count": 2}

    event = _event(payload=payload)
    payload["source_unit_count"] = 3

    assert isinstance(event.payload, MappingProxyType)
    assert event.payload["source_unit_count"] == 2
    with pytest.raises(TypeError):
        cast(dict[str, object], event.payload)["source_unit_count"] = 4


def test_workflow_event_requires_timezone_aware_occurred_at() -> None:
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        _event(occurred_at=datetime(2026, 6, 11, 12, 0))


def test_workflow_event_rejects_non_positive_sequence_number_when_provided() -> None:
    with pytest.raises(ValueError, match="sequence_number must be > 0"):
        _event(sequence_number=0)

    with pytest.raises(ValueError, match="sequence_number must be > 0"):
        _event(sequence_number=-1)
