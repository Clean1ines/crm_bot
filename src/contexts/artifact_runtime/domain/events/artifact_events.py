from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)


@dataclass(frozen=True, slots=True)
class ArtifactDomainEvent:
    artifact_ref: ArtifactRef
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ArtifactStored(ArtifactDomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactValidated(ArtifactDomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactRejected(ArtifactDomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactSuperseded(ArtifactDomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactExpired(ArtifactDomainEvent):
    final_status: ArtifactStatus = ArtifactStatus.EXPIRED
