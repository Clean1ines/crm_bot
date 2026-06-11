from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_event_cursor import (
    WorkflowEventCursor,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def test_workflow_event_cursor_starts_at_sequence_zero() -> None:
    cursor = WorkflowEventCursor(
        consumer_ref=WorkflowConsumerRef("knowledge-extraction-saga"),
        last_seen_sequence_number=0,
        updated_at=_now(),
    )

    assert cursor.last_seen_sequence_number == 0


def test_workflow_event_cursor_advances_forward() -> None:
    cursor = WorkflowEventCursor(
        consumer_ref=WorkflowConsumerRef("knowledge-extraction-saga"),
        last_seen_sequence_number=0,
        updated_at=_now(),
    )

    advanced = cursor.advance_to(3, updated_at=_now())

    assert advanced.consumer_ref == cursor.consumer_ref
    assert advanced.last_seen_sequence_number == 3
    assert advanced.updated_at == _now()


def test_workflow_event_cursor_rejects_backwards_advance() -> None:
    cursor = WorkflowEventCursor(
        consumer_ref=WorkflowConsumerRef("knowledge-extraction-saga"),
        last_seen_sequence_number=5,
        updated_at=_now(),
    )

    with pytest.raises(ValueError, match="cannot move cursor backwards"):
        cursor.advance_to(4, updated_at=_now())


def test_workflow_event_cursor_requires_timezone_aware_updated_at() -> None:
    with pytest.raises(ValueError, match="updated_at must be timezone-aware"):
        WorkflowEventCursor(
            consumer_ref=WorkflowConsumerRef("knowledge-extraction-saga"),
            last_seen_sequence_number=0,
            updated_at=datetime(2026, 6, 11, 12, 0),
        )


def test_workflow_event_cursor_rejects_negative_start_sequence() -> None:
    with pytest.raises(ValueError, match="last_seen_sequence_number must be >= 0"):
        WorkflowEventCursor(
            consumer_ref=WorkflowConsumerRef("knowledge-extraction-saga"),
            last_seen_sequence_number=-1,
            updated_at=_now(),
        )
