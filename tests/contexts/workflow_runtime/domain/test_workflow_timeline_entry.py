from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import cast

import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _entry() -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id="entry-1",
        workflow_run_id="workflow-1",
        event_type="SOURCE_UNITS_CREATED",
        phase="SOURCE_INGESTION",
        severity=WorkflowTimelineSeverity.INFO,
        message="Source units created",
        payload_summary={"source_unit_count": 2},
        occurred_at=_now(),
    )


def test_timeline_entry_rejects_empty_message() -> None:
    with pytest.raises(ValueError, match="message must be non-empty"):
        WorkflowTimelineEntry(
            timeline_entry_id="entry-1",
            workflow_run_id="workflow-1",
            event_type="SOURCE_UNITS_CREATED",
            phase="SOURCE_INGESTION",
            severity=WorkflowTimelineSeverity.INFO,
            message=" ",
            payload_summary={},
            occurred_at=_now(),
        )


def test_timeline_entry_freezes_payload_summary() -> None:
    entry = _entry()

    assert isinstance(entry.payload_summary, MappingProxyType)
    with pytest.raises(TypeError):
        cast(dict[str, object], entry.payload_summary)["x"] = 1


def test_timeline_entry_requires_timezone_aware_occurred_at() -> None:
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        WorkflowTimelineEntry(
            timeline_entry_id="entry-1",
            workflow_run_id="workflow-1",
            event_type="SOURCE_UNITS_CREATED",
            phase="SOURCE_INGESTION",
            severity=WorkflowTimelineSeverity.INFO,
            message="Source units created",
            payload_summary={},
            occurred_at=datetime(2026, 6, 11, 12, 0),
        )
