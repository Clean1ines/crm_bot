from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken


@dataclass(frozen=True, slots=True)
class WorkItemAttemptDispatchForExecution:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    lease_token: LeaseToken
    worker_ref: str
    dispatch_payload: Mapping[str, object]
    started_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")

        if not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be int")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")

        if not isinstance(self.lease_token, LeaseToken):
            raise TypeError("lease_token must be LeaseToken")

        _require_non_empty_text(self.worker_ref, field_name="worker_ref")

        if not isinstance(self.dispatch_payload, Mapping):
            raise TypeError("dispatch_payload must be Mapping")

        _require_timezone_aware(self.started_at, field_name="started_at")


class WorkItemAttemptDispatchReadRepositoryPort(Protocol):
    async def get_dispatch_for_execution(
        self,
        *,
        attempt_id: str,
    ) -> WorkItemAttemptDispatchForExecution | None: ...


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
