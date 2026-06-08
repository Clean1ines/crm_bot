from __future__ import annotations

from typing import Protocol, TypeAlias

from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.events.draft_claim_observation_events import (
    DraftClaimObservationsApplied,
)


DraftClaimObservationApplicationEvent: TypeAlias = DraftClaimObservationsApplied


class DraftClaimObservationApplicationUnitOfWorkPort(Protocol):
    def save_draft_claim_observations(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None: ...

    def append_event(
        self,
        event: DraftClaimObservationApplicationEvent,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
