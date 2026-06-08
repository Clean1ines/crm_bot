from __future__ import annotations

from typing import Protocol

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)


class ArtifactRepositoryPort(Protocol):
    """Read/write repository boundary for generic pipeline artifacts.

    Artifact Runtime stores artifact lifecycle, lineage and payload opacity only.
    Business interpretation of artifact payload belongs to caller contexts.
    """

    def save(self, artifact: PipelineArtifact) -> None:
        """Persist a pipeline artifact checkpoint."""

    def get(self, artifact_ref: ArtifactRef) -> PipelineArtifact | None:
        """Load a pipeline artifact by opaque reference."""

    def list_by_parent_ref(
        self,
        parent_ref: ArtifactRef,
    ) -> tuple[PipelineArtifact, ...]:
        """List artifacts derived from the given parent artifact reference."""

    def list_by_kind(
        self,
        artifact_kind: ArtifactKind,
    ) -> tuple[PipelineArtifact, ...]:
        """List artifacts by caller-owned artifact kind."""

    def list_by_kind_and_status(
        self,
        *,
        artifact_kind: ArtifactKind,
        status: ArtifactStatus,
    ) -> tuple[PipelineArtifact, ...]:
        """List artifacts by caller-owned artifact kind and lifecycle status."""
