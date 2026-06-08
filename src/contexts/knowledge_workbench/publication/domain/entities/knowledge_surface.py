from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.consolidated_surface_ref import (
    ConsolidatedSurfaceRef,
)
from src.contexts.knowledge_workbench.publication.domain.value_objects.knowledge_surface_ref import (
    KnowledgeSurfaceRef,
)


@dataclass(frozen=True, slots=True)
class KnowledgeSurface:
    surface_ref: KnowledgeSurfaceRef
    source_consolidated_surface_ref: ConsolidatedSurfaceRef
    canonical_intent: str
    answer: str
    published_at: datetime

    def __post_init__(self) -> None:
        if not self.canonical_intent or not self.canonical_intent.strip():
            raise ValueError("KnowledgeSurface.canonical_intent must be non-empty")
        if not self.answer or not self.answer.strip():
            raise ValueError("KnowledgeSurface.answer must be non-empty")
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("KnowledgeSurface.published_at must be timezone-aware")
