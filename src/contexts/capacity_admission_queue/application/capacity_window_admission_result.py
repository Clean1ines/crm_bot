from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CapacityWindowAdmissionSkippedReason(StrEnum):
    CAPACITY_ADMISSION_DISABLED = "capacity_admission_disabled"
    NO_SELECTABLE_WORK_ITEM = "no_selectable_work_item"
    NO_CAPACITY = "no_capacity"
    ACTIVE_LEASED_WAIT = "active_leased_wait"
    PROJECTION_CONFLICT = "projection_conflict"
    EXECUTION_LEASE_LOST = "execution_lease_lost"


@dataclass(frozen=True, slots=True)
class CapacityAdmissionLaneSummary:
    work_kind: str | None = None
    provider: str | None = None
    account_ref: str | None = None
    model_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CapacityAdmissionCapacityReservationSummary:
    reserved_count: int = 0
    payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CapacityAdmissionDispatchContextSummary:
    work_item_id: str | None = None
    attempt_id: str | None = None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CapacityAdmissionFrontendEventSummary:
    event_kind: str = "capacity_admission_disabled"
    payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CapacityWindowAdmissionPassResult:
    admitted_count: int = 0
    skipped_count: int = 0
    leased_count: int = 0
    started_attempt_count: int = 0
    commands: tuple[object, ...] = ()
    events: tuple[object, ...] = ()
    skipped_reason: CapacityWindowAdmissionSkippedReason | str | None = (
        CapacityWindowAdmissionSkippedReason.CAPACITY_ADMISSION_DISABLED
    )
    lane_summary: CapacityAdmissionLaneSummary | None = None
    reservation_summary: CapacityAdmissionCapacityReservationSummary | None = None
    dispatch_context_summary: CapacityAdmissionDispatchContextSummary | None = None
    frontend_event_summary: CapacityAdmissionFrontendEventSummary | None = None
    metadata: dict[str, Any] | None = None
