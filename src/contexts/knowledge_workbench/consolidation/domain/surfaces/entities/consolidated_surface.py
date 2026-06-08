from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.canonical_intent import (
    CanonicalIntent,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.consolidated_surface_ref import (
    ConsolidatedSurfaceRef,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.ontology_tag import (
    OntologyTag,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_evidence_ref import (
    SurfaceEvidenceRef,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_kind import (
    SurfaceKind,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_relation import (
    SurfaceRelation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)


@dataclass(frozen=True, slots=True)
class ConsolidatedSurface:
    surface_ref: ConsolidatedSurfaceRef
    canonical_intent: CanonicalIntent
    answer: str
    surface_kind: SurfaceKind
    source_observation_refs: tuple[DraftClaimObservationRef, ...]
    evidence_refs: tuple[SurfaceEvidenceRef, ...]
    ontology_tags: tuple[OntologyTag, ...]
    relations: tuple[SurfaceRelation, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.answer or not self.answer.strip():
            raise ValueError("ConsolidatedSurface.answer must be non-empty")
        if not self.source_observation_refs:
            raise ValueError(
                "ConsolidatedSurface.source_observation_refs must be non-empty"
            )
        if len(set(self.source_observation_refs)) != len(self.source_observation_refs):
            raise ValueError(
                "ConsolidatedSurface.source_observation_refs must not contain duplicates"
            )
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("ConsolidatedSurface.created_at must be timezone-aware")
