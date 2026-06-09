from __future__ import annotations

from typing import Protocol, TypeAlias

from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import (
    DraftClaimObservationProvenanceCandidate,
)
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

    def save_draft_claim_observation_provenance_candidates(
        self,
        candidates: tuple[DraftClaimObservationProvenanceCandidate, ...],
    ) -> None: ...

    def append_event(self, event: DraftClaimObservationApplicationEvent) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class AsyncDraftClaimObservationApplicationUnitOfWorkPort(Protocol):
    async def save_draft_claim_observations(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None: ...

    async def save_draft_claim_observation_provenance_candidates(
        self,
        candidates: tuple[DraftClaimObservationProvenanceCandidate, ...],
    ) -> None: ...

    async def append_event(
        self, event: DraftClaimObservationApplicationEvent
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
