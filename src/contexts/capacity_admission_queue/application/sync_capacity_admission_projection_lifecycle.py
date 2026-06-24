from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)


CAPACITY_ADMISSION_PROJECTED_LIFECYCLE_STATUSES = frozenset(
    {
        "ready",
        "leased",
        "retryable_failed",
        "completed",
        "terminal_failed",
        "cancelled",
        "split_superseded",
        "user_action_required",
    }
)


@dataclass(frozen=True, slots=True)
class CapacityAdmissionProjectionLifecycleUpdate:
    work_item_id: str
    status: str
    changed_at: datetime
    retry_plan: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.work_item_id, "work_item_id")
        _require_known_projection_status(self.status)
        _require_timezone_aware(self.changed_at, "changed_at")

        if self.status == "retryable_failed":
            if self.retry_plan is None:
                raise ValueError("retry_plan is required for retryable_failed")
            _require_non_empty(self.retry_plan, "retry_plan")
            return

        if self.retry_plan is not None:
            raise ValueError("retry_plan is only allowed for retryable_failed")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionProjectionLifecycleSyncResult:
    work_item_id: str
    lane_key: CapacityAdmissionLaneKey
    previous_status: str
    status: str
    retry_plan: str | None
    event_type: str
    reason: str
    event_id: UUID

    def __post_init__(self) -> None:
        _require_non_empty(self.work_item_id, "work_item_id")
        _require_known_projection_status(self.previous_status)
        _require_known_projection_status(self.status)
        _require_non_empty(self.event_type, "event_type")
        _require_non_empty(self.reason, "reason")
        if self.status == "retryable_failed":
            if self.retry_plan is None:
                raise ValueError("retry_plan is required for retryable_failed")
            _require_non_empty(self.retry_plan, "retry_plan")
        elif self.retry_plan is not None:
            raise ValueError("retry_plan is only allowed for retryable_failed")


class CapacityAdmissionProjectionLifecycleSynchronizerPort(Protocol):
    async def sync_projection_lifecycle(
        self,
        update: CapacityAdmissionProjectionLifecycleUpdate,
    ) -> CapacityAdmissionProjectionLifecycleSyncResult | None:
        """Mirror an Execution Runtime lifecycle status into admission projection."""


@dataclass(frozen=True, slots=True)
class SyncCapacityAdmissionProjectionLifecycle:
    projection_lifecycle_synchronizer: (
        CapacityAdmissionProjectionLifecycleSynchronizerPort
    )

    async def execute(
        self,
        update: CapacityAdmissionProjectionLifecycleUpdate,
    ) -> CapacityAdmissionProjectionLifecycleSyncResult | None:
        return await self.projection_lifecycle_synchronizer.sync_projection_lifecycle(
            update
        )


def _require_known_projection_status(value: str) -> None:
    if value not in CAPACITY_ADMISSION_PROJECTED_LIFECYCLE_STATUSES:
        raise ValueError("status must be a known capacity admission projection status")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
