from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType


def _missing_updated_at() -> datetime:
    raise ValueError("updated_at is required")


@dataclass(frozen=True, slots=True)
class WorkflowProgressSnapshot:
    workflow_run_id: str
    current_phase: str
    workflow_status: str
    total_work_items: int = 0
    scheduled_work_items: int = 0
    running_work_items: int = 0
    completed_work_items: int = 0
    deferred_work_items: int = 0
    retryable_failed_work_items: int = 0
    terminal_failed_work_items: int = 0
    blocked_work_items: int = 0
    domain_counters: Mapping[str, int] = field(default_factory=dict)
    started_at: datetime | None = None
    updated_at: datetime = field(default_factory=_missing_updated_at)
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.current_phase, "current_phase")
        _require_non_empty_text(self.workflow_status, "workflow_status")
        for field_name, value in (
            ("total_work_items", self.total_work_items),
            ("scheduled_work_items", self.scheduled_work_items),
            ("running_work_items", self.running_work_items),
            ("completed_work_items", self.completed_work_items),
            ("deferred_work_items", self.deferred_work_items),
            ("retryable_failed_work_items", self.retryable_failed_work_items),
            ("terminal_failed_work_items", self.terminal_failed_work_items),
            ("blocked_work_items", self.blocked_work_items),
        ):
            _require_non_negative_int(value, field_name)
        if self.started_at is not None:
            _require_timezone_aware(self.started_at, "started_at")
        _require_timezone_aware(self.updated_at, "updated_at")
        if self.completed_at is not None:
            _require_timezone_aware(self.completed_at, "completed_at")
        object.__setattr__(
            self,
            "domain_counters",
            MappingProxyType(_validated_domain_counters(self.domain_counters)),
        )


def _validated_domain_counters(
    counters: Mapping[str, int],
) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in counters.items():
        _require_non_empty_text(key, "domain_counters key")
        _require_non_negative_int(value, f"domain_counters[{key}]")
        result[key] = value
    return result


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
