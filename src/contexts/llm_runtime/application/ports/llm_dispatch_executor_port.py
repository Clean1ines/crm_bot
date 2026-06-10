from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class LlmDispatchExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"
    DEFERRED = "deferred"


_REQUIRED_DISPATCH_PAYLOAD_KEYS = frozenset(
    (
        "work_item_id",
        "schedule_payload",
        "llm_allocation",
        "llm_execution_settings",
    ),
)


@dataclass(frozen=True, slots=True)
class LlmDispatchExecutionInput:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    dispatch_payload: Mapping[str, object]
    started_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")

        if not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be int")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")

        if not isinstance(self.dispatch_payload, Mapping):
            raise TypeError("dispatch_payload must be Mapping")
        missing_keys = tuple(
            key
            for key in sorted(_REQUIRED_DISPATCH_PAYLOAD_KEYS)
            if key not in self.dispatch_payload
        )
        if missing_keys:
            raise ValueError(
                "dispatch_payload missing required keys: " + ", ".join(missing_keys),
            )

        _require_timezone_aware(self.started_at, field_name="started_at")


@dataclass(frozen=True, slots=True)
class LlmDispatchExecutionResult:
    status: LlmDispatchExecutionStatus
    finished_at: datetime
    output_payload: Mapping[str, object] | None = None
    error_kind: str | None = None
    next_attempt_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LlmDispatchExecutionStatus):
            raise TypeError("status must be LlmDispatchExecutionStatus")
        _require_timezone_aware(self.finished_at, field_name="finished_at")

        if self.output_payload is not None and not isinstance(
            self.output_payload,
            Mapping,
        ):
            raise TypeError("output_payload must be Mapping when provided")

        if self.error_kind is not None:
            _require_non_empty_text(self.error_kind, field_name="error_kind")

        if self.next_attempt_at is not None:
            _require_timezone_aware(
                self.next_attempt_at,
                field_name="next_attempt_at",
            )
            if self.next_attempt_at <= self.finished_at:
                raise ValueError("next_attempt_at must be after finished_at")

        if self.status is LlmDispatchExecutionStatus.SUCCEEDED:
            if self.output_payload is None:
                raise ValueError("output_payload is required for succeeded result")
            if self.error_kind is not None:
                raise ValueError("error_kind must be None for succeeded result")
            if self.next_attempt_at is not None:
                raise ValueError("next_attempt_at must be None for succeeded result")
            return

        if self.error_kind is None:
            raise ValueError("error_kind is required for failed/deferred results")

        if (
            self.status is LlmDispatchExecutionStatus.DEFERRED
            and self.next_attempt_at is None
        ):
            raise ValueError("next_attempt_at is required for deferred result")


class LlmDispatchExecutorPort(Protocol):
    async def execute_dispatch(
        self,
        execution_input: LlmDispatchExecutionInput,
    ) -> LlmDispatchExecutionResult: ...


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
