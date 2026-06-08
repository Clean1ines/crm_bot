from __future__ import annotations

from dataclasses import dataclass

from src.contexts.artifact_runtime.application.ports.artifact_repository_port import (
    ArtifactRepositoryPort,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)


@dataclass(frozen=True, slots=True)
class ListArtifactsByKindCommand:
    artifact_kind: ArtifactKind
    status: ArtifactStatus | None = None


@dataclass(frozen=True, slots=True)
class ListArtifactsByKindResult:
    artifacts: tuple[PipelineArtifact, ...]


class ListArtifactsByKind:
    """Read artifacts by caller-owned kind and optional lifecycle status."""

    def __init__(self, *, repository: ArtifactRepositoryPort) -> None:
        self._repository = repository

    def execute(self, command: ListArtifactsByKindCommand) -> ListArtifactsByKindResult:
        if command.status is None:
            artifacts = self._repository.list_by_kind(command.artifact_kind)
        else:
            artifacts = self._repository.list_by_kind_and_status(
                artifact_kind=command.artifact_kind,
                status=command.status,
            )

        return ListArtifactsByKindResult(artifacts=artifacts)
