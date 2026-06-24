from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)


@dataclass(frozen=True, slots=True)
class CapacityAdmissionProjectionLease:
    work_item_id: str
    lane_key: CapacityAdmissionLaneKey
    leased_at: datetime
    lease_reason: str = "capacity_window_admitted"

    def __post_init__(self) -> None:
        _require_non_empty(self.work_item_id, "work_item_id")
        _require_timezone_aware(self.leased_at, "leased_at")
        _require_non_empty(self.lease_reason, "lease_reason")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionProjectionLeaseResult:
    work_item_id: str
    lane_key: CapacityAdmissionLaneKey
    previous_status: str
    status: str
    event_id: UUID

    def __post_init__(self) -> None:
        _require_non_empty(self.work_item_id, "work_item_id")
        if self.previous_status not in {"ready", "retryable_failed"}:
            raise ValueError("previous_status must be ready or retryable_failed")
        if self.status != "leased":
            raise ValueError("status must be leased")


class CapacityAdmissionProjectionAdmitterPort(Protocol):
    async def admit_projection_work_item(
        self,
        lease: CapacityAdmissionProjectionLease,
    ) -> CapacityAdmissionProjectionLeaseResult | None:
        """Mark selected projection row as leased if it is still admissible."""


@dataclass(frozen=True, slots=True)
class AdmitCapacityAdmissionWorkItem:
    projection_admitter: CapacityAdmissionProjectionAdmitterPort

    async def execute(
        self,
        lease: CapacityAdmissionProjectionLease,
    ) -> CapacityAdmissionProjectionLeaseResult | None:
        return await self.projection_admitter.admit_projection_work_item(lease)


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
