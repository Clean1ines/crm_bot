from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind


@dataclass(frozen=True, slots=True)
class WorkItemRetryActionRecord:
    work_item_id: str
    dispatch_attempt_id: str
    next_action_kind: str
    next_model_strategy: str | None
    requires_source_split: bool
    next_run_after: datetime | None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.work_item_id, "work_item_id")
        _require_non_empty_text(self.dispatch_attempt_id, "dispatch_attempt_id")
        _require_non_empty_text(self.next_action_kind, "next_action_kind")
        if self.next_model_strategy is not None:
            _require_non_empty_text(self.next_model_strategy, "next_model_strategy")
        if not isinstance(self.requires_source_split, bool):
            raise TypeError("requires_source_split must be bool")
        if self.next_run_after is not None:
            _require_timezone_aware(self.next_run_after, "next_run_after")


@dataclass(frozen=True, slots=True)
class WorkItemRetryActionSummary:
    workflow_run_id: str
    work_kind: WorkKind
    retry_same_model_count: int
    retry_empty_claims_check_model_count: int
    retry_fallback_model_count: int
    retry_larger_output_model_count: int
    retry_larger_input_model_count: int
    split_required_count: int
    defer_until_capacity_reset_count: int
    pause_for_daily_limit_reset_count: int
    request_user_low_quality_continue_or_wait_count: int
    next_run_after: datetime | None
    records: tuple[WorkItemRetryActionRecord, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        for field_name, value in (
            ("retry_same_model_count", self.retry_same_model_count),
            (
                "retry_empty_claims_check_model_count",
                self.retry_empty_claims_check_model_count,
            ),
            ("retry_fallback_model_count", self.retry_fallback_model_count),
            (
                "retry_larger_output_model_count",
                self.retry_larger_output_model_count,
            ),
            (
                "retry_larger_input_model_count",
                self.retry_larger_input_model_count,
            ),
            ("split_required_count", self.split_required_count),
            (
                "defer_until_capacity_reset_count",
                self.defer_until_capacity_reset_count,
            ),
            (
                "pause_for_daily_limit_reset_count",
                self.pause_for_daily_limit_reset_count,
            ),
            (
                "request_user_low_quality_continue_or_wait_count",
                self.request_user_low_quality_continue_or_wait_count,
            ),
        ):
            _require_non_negative_int(value, field_name)
        if self.next_run_after is not None:
            _require_timezone_aware(self.next_run_after, "next_run_after")
        if not isinstance(self.records, tuple):
            raise TypeError("records must be tuple")
        for record in self.records:
            if not isinstance(record, WorkItemRetryActionRecord):
                raise TypeError("records must contain WorkItemRetryActionRecord")

    @property
    def has_retry_actions(self) -> bool:
        return (
            self.retry_same_model_count
            + self.retry_empty_claims_check_model_count
            + self.retry_fallback_model_count
            + self.retry_larger_output_model_count
            + self.retry_larger_input_model_count
            + self.split_required_count
            + self.defer_until_capacity_reset_count
            + self.pause_for_daily_limit_reset_count
            + self.request_user_low_quality_continue_or_wait_count
        ) > 0

    def to_payload(self) -> dict[str, object]:
        return {
            "workflow_run_id": self.workflow_run_id,
            "work_kind": self.work_kind.value,
            "retry_same_model_count": self.retry_same_model_count,
            "retry_empty_claims_check_model_count": (
                self.retry_empty_claims_check_model_count
            ),
            "retry_fallback_model_count": self.retry_fallback_model_count,
            "retry_larger_output_model_count": (self.retry_larger_output_model_count),
            "retry_larger_input_model_count": (self.retry_larger_input_model_count),
            "split_required_count": self.split_required_count,
            "defer_until_capacity_reset_count": (self.defer_until_capacity_reset_count),
            "pause_for_daily_limit_reset_count": (
                self.pause_for_daily_limit_reset_count
            ),
            "request_user_low_quality_continue_or_wait_count": (
                self.request_user_low_quality_continue_or_wait_count
            ),
            "next_run_after": self.next_run_after.isoformat()
            if self.next_run_after is not None
            else None,
        }


class ClaimBuilderRetryActionReadRepositoryPort(Protocol):
    async def summarize_retry_actions(
        self,
        *,
        workflow_run_id: str,
        work_kind: WorkKind,
        now: datetime,
    ) -> WorkItemRetryActionSummary: ...


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
