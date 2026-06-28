from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionLaneTarget,
)


class CapacityAdmissionLaneTargetResolverPort(Protocol):
    def resolve(self, work_kind: str) -> CapacityAdmissionLaneTarget | None: ...

    def resolve_lane_target_for_work_kind(
        self,
        work_kind: str,
    ) -> CapacityAdmissionLaneTarget | None: ...


@dataclass(frozen=True, slots=True)
class CapacityAdmissionLaneTargetRegistry:
    targets_by_work_kind: dict[str, CapacityAdmissionLaneTarget]

    def resolve(self, work_kind: str) -> CapacityAdmissionLaneTarget | None:
        return self.targets_by_work_kind.get(work_kind)

    def resolve_lane_target_for_work_kind(
        self,
        work_kind: str,
    ) -> CapacityAdmissionLaneTarget | None:
        return self.resolve(work_kind)
