from __future__ import annotations

from dataclasses import dataclass

from src.contexts.artifact_runtime.application.ports.artifact_repository_port import (
    ArtifactRepositoryPort,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef


@dataclass(frozen=True, slots=True)
class LoadArtifactCommand:
    artifact_ref: ArtifactRef


@dataclass(frozen=True, slots=True)
class LoadArtifactResult:
    artifact: PipelineArtifact | None


class LoadArtifact:
    """Read a pipeline artifact checkpoint by opaque reference."""

    def __init__(self, *, repository: ArtifactRepositoryPort) -> None:
        self._repository = repository

    def execute(self, command: LoadArtifactCommand) -> LoadArtifactResult:
        return LoadArtifactResult(
            artifact=self._repository.get(command.artifact_ref),
        )
