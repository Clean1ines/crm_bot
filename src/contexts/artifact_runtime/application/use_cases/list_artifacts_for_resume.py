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
class ListArtifactsForResumeCommand:
    parent_ref: ArtifactRef


@dataclass(frozen=True, slots=True)
class ListArtifactsForResumeResult:
    artifacts: tuple[PipelineArtifact, ...]


class ListArtifactsForResume:
    """Read child artifacts that can act as resume checkpoints."""

    def __init__(self, *, repository: ArtifactRepositoryPort) -> None:
        self._repository = repository

    def execute(
        self,
        command: ListArtifactsForResumeCommand,
    ) -> ListArtifactsForResumeResult:
        return ListArtifactsForResumeResult(
            artifacts=self._repository.list_by_parent_ref(command.parent_ref),
        )
