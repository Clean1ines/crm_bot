from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionLaneTarget,
)


class CapacityAdmissionLaneTargetResolverPort(Protocol):
    def resolve_lane_target_for_work_kind(
        self,
        work_kind: str,
    ) -> CapacityAdmissionLaneTarget | None:
        """Return target lane for a work kind, or None when admission is disabled."""


@dataclass(frozen=True, slots=True)
class CapacityAdmissionLaneTargetRegistry:
    targets_by_work_kind: dict[str, CapacityAdmissionLaneTarget]

    def __post_init__(self) -> None:
        if not isinstance(self.targets_by_work_kind, dict):
            raise TypeError("targets_by_work_kind must be dict")
        for work_kind, target in self.targets_by_work_kind.items():
            _require_non_empty_text(work_kind, "work_kind")
            if not isinstance(target, CapacityAdmissionLaneTarget):
                raise TypeError(
                    "targets_by_work_kind values must be CapacityAdmissionLaneTarget"
                )

    def resolve_lane_target_for_work_kind(
        self,
        work_kind: str,
    ) -> CapacityAdmissionLaneTarget | None:
        _require_non_empty_text(work_kind, "work_kind")
        return self.targets_by_work_kind.get(work_kind)


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
