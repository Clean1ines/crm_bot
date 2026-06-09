from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import PipelineArtifact
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifactAsync,
    ApplyDraftClaimObservationArtifactResult,
)


class ArtifactLoaderPort(Protocol):
    async def load_artifact(
        self,
        artifact_ref: ArtifactRef,
    ) -> PipelineArtifact | None: ...


@dataclass(frozen=True, slots=True)
class ApplyDraftClaimObservationArtifactOnArtifactStoredCommand:
    event: ArtifactStored
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ApplyDraftClaimObservationArtifactOnArtifactStoredResult:
    artifact_ref: ArtifactRef
    status: str
    apply_result: ApplyDraftClaimObservationArtifactResult | None = None


class ApplyDraftClaimObservationArtifactOnArtifactStored:
    def __init__(
        self,
        *,
        artifact_loader: ArtifactLoaderPort,
        apply_use_case: ApplyDraftClaimObservationArtifactAsync,
    ) -> None:
        self._artifact_loader = artifact_loader
        self._apply_use_case = apply_use_case
