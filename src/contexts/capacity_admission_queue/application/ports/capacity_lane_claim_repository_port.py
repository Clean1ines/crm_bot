from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)


@dataclass(frozen=True, slots=True)
class CapacityLaneClaim:
    lane_id: str
    lane_key: CapacityAdmissionLaneKey
    claimed_by: str
    claimed_until: datetime
    claim_version: int


class CapacityLaneClaimRepositoryPort(Protocol):
    async def claim_dirty_lane(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        worker_ref: str,
        now: datetime,
        claim_ttl_seconds: int,
    ) -> CapacityLaneClaim | None: ...

    async def release_lane_claim(
        self,
        *,
        lane_id: str,
        worker_ref: str,
        now: datetime,
    ) -> None: ...

    async def clear_dirty_flag(
        self,
        *,
        lane_id: str,
        worker_ref: str,
        now: datetime,
    ) -> None: ...
