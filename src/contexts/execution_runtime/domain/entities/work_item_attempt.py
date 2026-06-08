from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WorkItemAttempt:
    """Execution attempt record for a WorkItem."""

    attempt_id: str
    work_item_id: str
    attempt_number: int
    started_at: datetime
    finished_at: datetime | None = None
    outcome_status: str | None = None
    error_kind: str | None = None

    def __post_init__(self) -> None:
        if not self.attempt_id or not self.attempt_id.strip():
            raise ValueError("WorkItemAttempt.attempt_id must be non-empty")
        if not self.work_item_id or not self.work_item_id.strip():
            raise ValueError("WorkItemAttempt.work_item_id must be non-empty")
        if self.attempt_number < 1:
            raise ValueError("WorkItemAttempt.attempt_number must be >= 1")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        if self.finished_at is not None:
            if self.finished_at.tzinfo is None or self.finished_at.utcoffset() is None:
                raise ValueError("finished_at must be timezone-aware")
            if self.finished_at < self.started_at:
                raise ValueError("finished_at must be >= started_at")
