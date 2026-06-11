from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class WorkflowTimelineSeverity(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class WorkflowTimelineEntry:
    timeline_entry_id: str
    workflow_run_id: str
    event_type: str
    phase: str
    severity: WorkflowTimelineSeverity
    message: str
    payload_summary: Mapping[str, object]
    occurred_at: datetime
    source_ref: str | None = None
    work_item_id: str | None = None
    attempt_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.timeline_entry_id, "timeline_entry_id")
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.event_type, "event_type")
        _require_non_empty_text(self.phase, "phase")
        if not isinstance(self.severity, WorkflowTimelineSeverity):
            raise TypeError("severity must be WorkflowTimelineSeverity")
        _require_non_empty_text(self.message, "message")
        _require_timezone_aware(self.occurred_at, "occurred_at")
        for field_name, value in (
            ("source_ref", self.source_ref),
            ("work_item_id", self.work_item_id),
            ("attempt_id", self.attempt_id),
        ):
            if value is not None:
                _require_non_empty_text(value, field_name)
        object.__setattr__(
            self,
            "payload_summary",
            MappingProxyType(dict(self.payload_summary)),
        )


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
