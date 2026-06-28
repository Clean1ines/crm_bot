from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CapacityAdmissionLaneTarget:
    provider: str
    account_ref: str | None
    model_ref: str


@dataclass(frozen=True, slots=True)
class CapacityAdmissionProjectionCandidate:
    work_item_id: str
    work_kind: str
    provider: str
    account_ref: str | None
    model_ref: str
    payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class BuildCapacityAdmissionProjectionCandidatesResult:
    candidates: tuple[CapacityAdmissionProjectionCandidate, ...] = ()


class BuildCapacityAdmissionProjectionCandidates:
    def execute(
        self, *args: object, **kwargs: object
    ) -> BuildCapacityAdmissionProjectionCandidatesResult:
        return BuildCapacityAdmissionProjectionCandidatesResult()
