from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import (
    ArtifactLineage,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    ArtifactPayload,
    JsonInputValue,
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
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_dispatch_artifact_provenance import (
    ClaimExtractionDispatchArtifactProvenance,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_artifact_parser import (
    EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
)


DISPATCH_PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND = ArtifactKind(
    "knowledge_workbench.claim_observations.raw",
)
DISPATCH_PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND = (
    EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND
)


@dataclass(frozen=True, slots=True)
class ClaimExtractionDispatchPromptAArtifacts:
    raw_output_artifact: PipelineArtifact
    parsed_output_artifact: PipelineArtifact


class ClaimExtractionDispatchPromptAArtifactFactory:
    def build(
        self,
        *,
        provenance: ClaimExtractionDispatchArtifactProvenance,
        raw_output: str,
        parsed_claims_payload: tuple[Mapping[str, JsonInputValue], ...],
        created_at: datetime,
        updated_at: datetime,
    ) -> ClaimExtractionDispatchPromptAArtifacts:
        _require_timezone_aware(created_at, "created_at")
        _require_timezone_aware(updated_at, "updated_at")

        raw_artifact = PipelineArtifact(
            artifact_ref=_artifact_ref(provenance, "raw"),
            artifact_kind=DISPATCH_PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
            payload=ArtifactPayload(
                provenance.to_raw_artifact_payload_fields(raw_output=raw_output),
            ),
            status=ArtifactStatus.STORED,
            visibility=ArtifactVisibility.INTERNAL,
            retention_policy=RetentionPolicy.temporary(),
            lineage=ArtifactLineage(),
            created_at=created_at,
            updated_at=updated_at,
        )
        parsed_artifact = PipelineArtifact(
            artifact_ref=_artifact_ref(provenance, "parsed"),
            artifact_kind=DISPATCH_PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
            payload=ArtifactPayload(
                provenance.to_parsed_artifact_payload_fields(
                    raw_artifact_ref=raw_artifact.artifact_ref,
                    claims=parsed_claims_payload,
                ),
            ),
            status=ArtifactStatus.VALIDATED,
            visibility=ArtifactVisibility.INTERNAL,
            retention_policy=RetentionPolicy.temporary(),
            lineage=ArtifactLineage(parent_refs=(raw_artifact.artifact_ref,)),
            created_at=created_at,
            updated_at=updated_at,
        )
        return ClaimExtractionDispatchPromptAArtifacts(
            raw_output_artifact=raw_artifact,
            parsed_output_artifact=parsed_artifact,
        )


def _artifact_ref(
    provenance: ClaimExtractionDispatchArtifactProvenance,
    suffix: str,
) -> ArtifactRef:
    return ArtifactRef(
        ":".join(
            (
                "claim-extraction-dispatch",
                provenance.workflow_run_id,
                provenance.stage_run_id,
                provenance.work_item_id,
                provenance.work_item_attempt_id,
                suffix,
            )
        )
    )


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
