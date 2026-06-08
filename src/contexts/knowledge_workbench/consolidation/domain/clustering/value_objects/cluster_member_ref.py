from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)


@dataclass(frozen=True, slots=True)
class ClusterMemberRef:
    value: DraftClaimObservationRef
