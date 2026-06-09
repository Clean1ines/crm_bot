from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import PipelineArtifact
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_artifact_provenance import (
    ClaimExtractionArtifactProvenance,
    InvalidClaimExtractionArtifactProvenance,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_prompt_a_artifact_factory import (
    PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifactAsync,
    ApplyDraftClaimObservationArtifactCommand,
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

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


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

    async def execute(
        self,
        command: ApplyDraftClaimObservationArtifactOnArtifactStoredCommand,
    ) -> ApplyDraftClaimObservationArtifactOnArtifactStoredResult:
        artifact_ref = command.event.artifact_ref
        artifact = await self._artifact_loader.load_artifact(artifact_ref)
        if artifact is None:
            return ApplyDraftClaimObservationArtifactOnArtifactStoredResult(
                artifact_ref=artifact_ref,
                status="ignored_missing_artifact",
            )
        if getattr(artifact, "artifact_kind") == PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND:
            return ApplyDraftClaimObservationArtifactOnArtifactStoredResult(
                artifact_ref=artifact_ref,
                status="ignored_invalid_prompt_a_provenance",
            )
        return ApplyDraftClaimObservationArtifactOnArtifactStoredResult(
            artifact_ref=artifact_ref,
            status="ignored_non_prompt_a_parsed_artifact",
        )
