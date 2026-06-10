from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WorkItemAttemptDispatchRecord:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    lease_token: str
    worker_ref: str
    schedule_payload: Mapping[str, object]
    llm_allocation_payload: Mapping[str, object]
    dispatch_payload: Mapping[str, object]
    started_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")
        if not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be int")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")
        _require_non_empty_text(self.lease_token, field_name="lease_token")
        _require_non_empty_text(self.worker_ref, field_name="worker_ref")
        _require_mapping(self.schedule_payload, field_name="schedule_payload")
        _require_mapping(
            self.llm_allocation_payload,
            field_name="llm_allocation_payload",
        )
        _require_mapping(self.dispatch_payload, field_name="dispatch_payload")
        _require_timezone_aware(self.started_at, field_name="started_at")


class WorkItemAttemptDispatchRepositoryPort(Protocol):
    async def save_started_dispatch_attempt(
        self,
        record: WorkItemAttemptDispatchRecord,
    ) -> None: ...


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_mapping(value: Mapping[str, object], *, field_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be Mapping")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
