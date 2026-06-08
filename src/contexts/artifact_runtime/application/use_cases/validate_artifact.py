from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.application.ports.artifact_unit_of_work_port import (
    ArtifactUnitOfWorkPort,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import (
    ArtifactValidated,
)


@dataclass(frozen=True, slots=True)
class ValidateArtifactCommand:
    artifact: PipelineArtifact
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ValidateArtifactResult:
    artifact: PipelineArtifact
    event: ArtifactValidated


class ValidateArtifact:
    """Validate a stored artifact and commit the lifecycle event atomically."""

    def __init__(self, *, unit_of_work: ArtifactUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, command: ValidateArtifactCommand) -> ValidateArtifactResult:
        artifact = command.artifact.validate(updated_at=command.occurred_at)
        event = ArtifactValidated(
            artifact_ref=artifact.artifact_ref,
            occurred_at=command.occurred_at,
        )

        try:
            self._unit_of_work.save_artifact(artifact)
            self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return ValidateArtifactResult(artifact=artifact, event=event)
