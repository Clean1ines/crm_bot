from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    event_id: WorkflowEventId
    event_type: str
    workflow_run_id: str
    payload: Mapping[str, object]
    occurred_at: datetime
    causation_command_id: WorkflowCommandId | None = None
    correlation_id: str | None = None
    sequence_number: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, WorkflowEventId):
            raise TypeError("event_id must be WorkflowEventId")
        _require_non_empty_text(self.event_type, field_name="event_type")
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        if self.causation_command_id is not None and not isinstance(
            self.causation_command_id,
            WorkflowCommandId,
        ):
            raise TypeError("causation_command_id must be WorkflowCommandId")
        if self.correlation_id is not None:
            _require_non_empty_text(self.correlation_id, field_name="correlation_id")
        if self.sequence_number is not None:
            if not isinstance(self.sequence_number, int):
                raise TypeError("sequence_number must be int")
            if self.sequence_number <= 0:
                raise ValueError("sequence_number must be > 0")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
