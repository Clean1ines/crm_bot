from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import cast

import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def test_progress_snapshot_rejects_negative_counters() -> None:
    with pytest.raises(ValueError, match="completed_work_items must be >= 0"):
        WorkflowProgressSnapshot(
            workflow_run_id="workflow-1",
            current_phase="SOURCE_INGESTION",
            workflow_status="RUNNING",
            completed_work_items=-1,
            updated_at=_now(),
        )


def test_progress_snapshot_freezes_domain_counters() -> None:
    counters = {"source_units": 2}

    snapshot = WorkflowProgressSnapshot(
        workflow_run_id="workflow-1",
        current_phase="SOURCE_INGESTION",
        workflow_status="RUNNING",
        domain_counters=counters,
        updated_at=_now(),
    )
    counters["source_units"] = 3

    assert isinstance(snapshot.domain_counters, MappingProxyType)
    assert snapshot.domain_counters["source_units"] == 2
    with pytest.raises(TypeError):
        cast(dict[str, int], snapshot.domain_counters)["source_units"] = 4


def test_progress_snapshot_requires_timezone_aware_updated_at() -> None:
    with pytest.raises(ValueError, match="updated_at must be timezone-aware"):
        WorkflowProgressSnapshot(
            workflow_run_id="workflow-1",
            current_phase="SOURCE_INGESTION",
            workflow_status="RUNNING",
            updated_at=datetime(2026, 6, 11, 12, 0),
        )
