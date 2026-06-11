from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)


@dataclass(frozen=True, slots=True)
class WorkflowEventCursor:
    consumer_ref: WorkflowConsumerRef
    last_seen_sequence_number: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.consumer_ref, WorkflowConsumerRef):
            raise TypeError("consumer_ref must be WorkflowConsumerRef")
        if not isinstance(self.last_seen_sequence_number, int):
            raise TypeError("last_seen_sequence_number must be int")
        if self.last_seen_sequence_number < 0:
            raise ValueError("last_seen_sequence_number must be >= 0")
        _require_timezone_aware(self.updated_at, field_name="updated_at")

    def advance_to(
        self,
        sequence_number: int,
        *,
        updated_at: datetime,
    ) -> WorkflowEventCursor:
        if not isinstance(sequence_number, int):
            raise TypeError("sequence_number must be int")
        if sequence_number < self.last_seen_sequence_number:
            raise ValueError("cannot move cursor backwards")
        return WorkflowEventCursor(
            consumer_ref=self.consumer_ref,
            last_seen_sequence_number=sequence_number,
            updated_at=updated_at,
        )


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
