from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind


@dataclass(frozen=True, slots=True)
class WorkItemProgressSummary:
    ready_count: int
    leased_count: int
    deferred_count: int
    retryable_failed_count: int
    completed_count: int
    terminal_failed_count: int
    cancelled_count: int
    split_superseded_count: int
    user_action_required_count: int
    total_count: int
    next_due_at: datetime | None = None
    due_deferred_count: int = 0
    due_retryable_failed_count: int = 0

    def __post_init__(self) -> None:
        for field_name, value in (
            ("ready_count", self.ready_count),
            ("leased_count", self.leased_count),
            ("deferred_count", self.deferred_count),
            ("retryable_failed_count", self.retryable_failed_count),
            ("completed_count", self.completed_count),
            ("terminal_failed_count", self.terminal_failed_count),
            ("cancelled_count", self.cancelled_count),
            ("split_superseded_count", self.split_superseded_count),
            ("user_action_required_count", self.user_action_required_count),
            ("total_count", self.total_count),
            ("due_deferred_count", self.due_deferred_count),
            ("due_retryable_failed_count", self.due_retryable_failed_count),
        ):
            _require_non_negative_int(value, field_name)

        if self.next_due_at is not None:
            _require_timezone_aware(self.next_due_at, "next_due_at")

        counted_total = (
            self.ready_count
            + self.leased_count
            + self.deferred_count
            + self.retryable_failed_count
            + self.completed_count
            + self.terminal_failed_count
            + self.cancelled_count
            + self.split_superseded_count
            + self.user_action_required_count
        )
        if counted_total != self.total_count:
            raise ValueError("summary status counts must add up to total_count")
        if self.due_deferred_count > self.deferred_count:
            raise ValueError("due_deferred_count cannot exceed deferred_count")
        if self.due_retryable_failed_count > self.retryable_failed_count:
            raise ValueError(
                "due_retryable_failed_count cannot exceed retryable_failed_count"
            )

    @property
    def due_waiting_count(self) -> int:
        return self.ready_count + self.retryable_failed_count

    @property
    def terminal_coverage_count(self) -> int:
        return (
            self.completed_count
            + self.terminal_failed_count
            + self.cancelled_count
            + self.split_superseded_count
            + self.user_action_required_count
        )

    @property
    def has_future_waiting_work(self) -> bool:
        return False

    def to_payload(self) -> dict[str, object]:
        return {
            "ready_count": self.ready_count,
            "leased_count": self.leased_count,
            "deferred_count": self.deferred_count,
            "retryable_failed_count": self.retryable_failed_count,
            "completed_count": self.completed_count,
            "terminal_failed_count": self.terminal_failed_count,
            "cancelled_count": self.cancelled_count,
            "split_superseded_count": self.split_superseded_count,
            "user_action_required_count": self.user_action_required_count,
            "total_count": self.total_count,
            "next_due_at": None,
            "due_deferred_count": self.due_deferred_count,
            "due_retryable_failed_count": self.due_retryable_failed_count,
        }


class WorkItemProgressReadRepositoryPort(Protocol):
    async def summarize_by_work_kind_and_workflow(
        self,
        *,
        workflow_run_id: str,
        work_kind: WorkKind,
        now: datetime,
    ) -> WorkItemProgressSummary: ...


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
