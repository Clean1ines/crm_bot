from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

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
class PipelineArtifact:
    """Generic stored result of a pipeline step.

    The entity owns storage lifecycle, payload opacity, lineage and retention only.
    """

    artifact_ref: ArtifactRef
    artifact_kind: ArtifactKind
    payload: ArtifactPayload
    status: ArtifactStatus
    visibility: ArtifactVisibility
    retention_policy: RetentionPolicy
    lineage: ArtifactLineage
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")

    def validate(self, *, updated_at: datetime) -> "PipelineArtifact":
        if self.status.is_terminal:
            raise ValueError(f"Cannot validate artifact from status {self.status}")
        return replace(self, status=ArtifactStatus.VALIDATED, updated_at=updated_at)

    def reject(self, *, updated_at: datetime) -> "PipelineArtifact":
        if self.status.is_terminal:
            raise ValueError(f"Cannot reject artifact from status {self.status}")
        return replace(self, status=ArtifactStatus.REJECTED, updated_at=updated_at)

    def supersede(self, *, updated_at: datetime) -> "PipelineArtifact":
        if self.status.is_terminal:
            raise ValueError(f"Cannot supersede artifact from status {self.status}")
        return replace(self, status=ArtifactStatus.SUPERSEDED, updated_at=updated_at)

    def expire(self, *, updated_at: datetime) -> "PipelineArtifact":
        if self.status.is_terminal:
            raise ValueError(f"Cannot expire artifact from status {self.status}")
        return replace(self, status=ArtifactStatus.EXPIRED, updated_at=updated_at)
