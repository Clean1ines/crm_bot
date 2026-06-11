from __future__ import annotations

from typing import Protocol, TypeAlias

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import (
    ArtifactExpired,
    ArtifactRejected,
    ArtifactStored,
    ArtifactSuperseded,
    ArtifactValidated,
)


ArtifactEvent: TypeAlias = (
    ArtifactStored
    | ArtifactValidated
    | ArtifactRejected
    | ArtifactSuperseded
    | ArtifactExpired
)


class ArtifactUnitOfWorkPort(Protocol):
    """Async transaction boundary for Artifact Runtime persistence lifecycle changes."""

    async def save_artifact(self, artifact: PipelineArtifact) -> None:
        """Persist artifact state."""

    async def append_event(self, event: ArtifactEvent) -> None:
        """Append durable artifact event to be committed with state change."""

    async def commit(self) -> None:
        """Commit transaction."""

    async def rollback(self) -> None:
        """Rollback transaction."""
