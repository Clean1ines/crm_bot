from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


class WorkflowCommandStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class WorkflowCommand:
    command_id: WorkflowCommandId
    command_type: str
    workflow_run_id: str
    idempotency_key: WorkflowIdempotencyKey
    payload: Mapping[str, object]
    status: WorkflowCommandStatus
    run_after: datetime
    created_at: datetime
    updated_at: datetime
    causation_event_id: WorkflowEventId | None = None
    correlation_id: str | None = None
    attempt_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, WorkflowCommandId):
            raise TypeError("command_id must be WorkflowCommandId")
        _require_non_empty_text(self.command_type, field_name="command_type")
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        if not isinstance(self.idempotency_key, WorkflowIdempotencyKey):
            raise TypeError("idempotency_key must be WorkflowIdempotencyKey")
        if not isinstance(self.status, WorkflowCommandStatus):
            raise TypeError("status must be WorkflowCommandStatus")
        _require_timezone_aware(self.run_after, field_name="run_after")
        _require_timezone_aware(self.created_at, field_name="created_at")
        _require_timezone_aware(self.updated_at, field_name="updated_at")
        if self.causation_event_id is not None and not isinstance(
            self.causation_event_id,
            WorkflowEventId,
        ):
            raise TypeError("causation_event_id must be WorkflowEventId")
        if self.correlation_id is not None:
            _require_non_empty_text(self.correlation_id, field_name="correlation_id")
        if not isinstance(self.attempt_count, int):
            raise TypeError("attempt_count must be int")
        if self.attempt_count < 0:
            raise ValueError("attempt_count must be >= 0")
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
