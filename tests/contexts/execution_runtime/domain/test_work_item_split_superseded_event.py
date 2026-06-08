from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemSplitSuperseded,
)


def test_work_item_split_superseded_event_is_generic_execution_event() -> None:
    occurred_at = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)

    event = WorkItemSplitSuperseded(
        work_item_id="work-1",
        occurred_at=occurred_at,
    )

    assert event.work_item_id == "work-1"
    assert event.occurred_at == occurred_at
    assert event.reason == "split_required"
