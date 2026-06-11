from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.application.ports.artifact_unit_of_work_port import (
    ArtifactUnitOfWorkPort,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactRejected


@dataclass(frozen=True, slots=True)
class RejectArtifactCommand:
    artifact: PipelineArtifact
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RejectArtifactResult:
    artifact: PipelineArtifact
    event: ArtifactRejected


class RejectArtifact:
    """Reject an artifact and commit the lifecycle event atomically."""

    def __init__(self, *, unit_of_work: ArtifactUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    async def execute(self, command: RejectArtifactCommand) -> RejectArtifactResult:
        artifact = command.artifact.reject(updated_at=command.occurred_at)
        event = ArtifactRejected(
            artifact_ref=artifact.artifact_ref,
            occurred_at=command.occurred_at,
        )

        try:
            await self._unit_of_work.save_artifact(artifact)
            await self._unit_of_work.append_event(event)
            await self._unit_of_work.commit()
        except Exception:
            await self._unit_of_work.rollback()
            raise

        return RejectArtifactResult(artifact=artifact, event=event)
