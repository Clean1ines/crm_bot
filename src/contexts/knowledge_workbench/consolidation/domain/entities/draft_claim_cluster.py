from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.consolidation.domain.value_objects.cluster_ref import (
    ClusterRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)


@dataclass(frozen=True, slots=True)
class DraftClaimCluster:
    cluster_ref: ClusterRef
    members: tuple[DraftClaimObservationRef, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.members:
            raise ValueError("DraftClaimCluster.members must be non-empty")
        if len(set(self.members)) != len(self.members):
            raise ValueError("DraftClaimCluster.members must not contain duplicates")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("DraftClaimCluster.created_at must be timezone-aware")
