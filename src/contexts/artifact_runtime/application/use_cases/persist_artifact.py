from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.application.ports.artifact_unit_of_work_port import (
    ArtifactUnitOfWorkPort,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import (
    ArtifactLineage,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    ArtifactPayload,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import (
    ArtifactVisibility,
)
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import (
    RetentionPolicy,
)


@dataclass(frozen=True, slots=True)
class PersistArtifactCommand:
    artifact_ref: ArtifactRef
    artifact_kind: ArtifactKind
    payload: ArtifactPayload
    visibility: ArtifactVisibility
    retention_policy: RetentionPolicy
    lineage: ArtifactLineage
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class PersistArtifactResult:
    artifact: PipelineArtifact
    event: ArtifactStored


class PersistArtifact:
    """Persist a new pipeline artifact and commit its event atomically.

    Artifact Runtime does not interpret artifact payload business meaning.
    The caller owns artifact_kind naming and payload semantics.
    """

    def __init__(self, *, unit_of_work: ArtifactUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    async def execute(self, command: PersistArtifactCommand) -> PersistArtifactResult:
        artifact = PipelineArtifact(
            artifact_ref=command.artifact_ref,
            artifact_kind=command.artifact_kind,
            payload=command.payload,
            status=ArtifactStatus.STORED,
            visibility=command.visibility,
            retention_policy=command.retention_policy,
            lineage=command.lineage,
            created_at=command.occurred_at,
            updated_at=command.occurred_at,
        )
        event = ArtifactStored(
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

        return PersistArtifactResult(
            artifact=artifact,
            event=event,
        )
