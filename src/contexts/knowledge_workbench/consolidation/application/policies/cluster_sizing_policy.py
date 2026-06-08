from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.consolidation.domain.clustering.entities.draft_claim_cluster import (
    DraftClaimCluster,
)
from src.contexts.knowledge_workbench.consolidation.domain.clustering.entities.draft_claim_subcluster import (
    DraftClaimSubcluster,
)
from src.contexts.knowledge_workbench.consolidation.domain.clustering.value_objects.subcluster_ref import (
    SubclusterRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)


@dataclass(frozen=True, slots=True)
class ClusterSizingInput:
    cluster: DraftClaimCluster
    max_members_per_request: int

    def __post_init__(self) -> None:
        if self.max_members_per_request <= 0:
            raise ValueError("max_members_per_request must be > 0")


@dataclass(frozen=True, slots=True)
class ClusterSizingResult:
    subclusters: tuple[DraftClaimSubcluster, ...]


class ClusterSizingPolicy:
    def split(
        self,
        input: ClusterSizingInput,
    ) -> ClusterSizingResult:
        chunks = self._chunks(
            members=input.cluster.members,
            chunk_size=input.max_members_per_request,
        )

        subclusters = tuple(
            DraftClaimSubcluster(
                subcluster_ref=SubclusterRef(
                    f"{input.cluster.cluster_ref.value}.subcluster.{index}"
                ),
                parent_cluster_ref=input.cluster.cluster_ref,
                members=chunk,
                created_at=input.cluster.created_at,
            )
            for index, chunk in enumerate(chunks)
        )

        return ClusterSizingResult(subclusters=subclusters)

    def _chunks(
        self,
        *,
        members: tuple[DraftClaimObservationRef, ...],
        chunk_size: int,
    ) -> tuple[tuple[DraftClaimObservationRef, ...], ...]:
        return tuple(
            members[index : index + chunk_size]
            for index in range(0, len(members), chunk_size)
        )
