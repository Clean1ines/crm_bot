from __future__ import annotations

from dataclasses import dataclass

from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef


@dataclass(frozen=True, slots=True)
class ArtifactLineage:
    """Parent references for a derived artifact."""

    parent_refs: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.parent_refs)) != len(self.parent_refs):
            raise ValueError("ArtifactLineage.parent_refs must not contain duplicates")
