from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.use_cases.supersede_waiting_work_items_for_split import (
    SupersedeWaitingWorkItemsForSplitCommand,
)


ROOT = Path(__file__).resolve().parents[5]


def _now() -> datetime:
    return datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def test_command_rejects_empty_work_item_ids() -> None:
    with pytest.raises(ValueError, match="work_item_ids"):
        SupersedeWaitingWorkItemsForSplitCommand(
            work_item_ids=(),
            occurred_at=_now(),
        )


def test_command_rejects_blank_work_item_id() -> None:
    with pytest.raises(ValueError, match="work_item_ids"):
        SupersedeWaitingWorkItemsForSplitCommand(
            work_item_ids=(" ",),
            occurred_at=_now(),
        )


def test_split_supersede_source_does_not_use_work_item_retry_timing() -> None:
    source = (
        ROOT / "src/contexts/execution_runtime/application/use_cases/"
        "supersede_waiting_work_items_for_split.py"
    ).read_text(encoding="utf-8")

    assert "WorkItemStatus.RETRYABLE_FAILED" in source
    assert "mark_split_superseded_waiting" in source
