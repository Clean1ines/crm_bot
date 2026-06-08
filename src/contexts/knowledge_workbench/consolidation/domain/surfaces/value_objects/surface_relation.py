from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.consolidated_surface_ref import (
    ConsolidatedSurfaceRef,
)


@dataclass(frozen=True, slots=True)
class SurfaceRelation:
    relation_kind: str
    target_surface_ref: ConsolidatedSurfaceRef

    def __post_init__(self) -> None:
        if not self.relation_kind or not self.relation_kind.strip():
            raise ValueError("SurfaceRelation.relation_kind must be non-empty")
