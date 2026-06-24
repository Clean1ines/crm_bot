from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionWorkItemProjectionCandidate,
)


@dataclass(frozen=True, slots=True)
class PersistCapacityAdmissionProjectionResult:
    persisted_count: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.persisted_count, bool)
            or not isinstance(self.persisted_count, int)
            or self.persisted_count < 0
        ):
            raise ValueError("persisted_count must be non-negative int")


class CapacityAdmissionProjectionWriterPort(Protocol):
    """Persistence boundary for capacity admission projection candidates."""

    async def persist_projection_candidates(
        self,
        candidates: tuple[CapacityAdmissionWorkItemProjectionCandidate, ...],
    ) -> PersistCapacityAdmissionProjectionResult:
        """Upsert admission projection rows and coalesce lane wakeups."""
