from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


@dataclass(frozen=True, slots=True)
class DraftClaimObservationsApplied:
    artifact_ref: ArtifactRef
    source_unit_ref: SourceUnitRef
    observation_count: int
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.observation_count < 0:
            raise ValueError("observation_count must be >= 0")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
