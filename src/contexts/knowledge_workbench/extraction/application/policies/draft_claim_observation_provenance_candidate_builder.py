from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    JsonInputValue,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_artifact_provenance import (
    ClaimExtractionArtifactProvenance,
    InvalidClaimExtractionArtifactProvenance,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


class InvalidDraftClaimObservationProvenanceCandidate(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DraftClaimObservationProvenanceCandidate:
    observation_ref: DraftClaimObservationRef
    source_unit_ref: SourceUnitRef
    workflow_run_id: str
    stage_run_id: str
    work_item_id: str
    work_item_attempt_id: str
    llm_task_id: str
    llm_attempt_id: str
    prompt_id: str
    prompt_version: str
    raw_artifact_ref: ArtifactRef
    parsed_artifact_ref: ArtifactRef
    claim_index: int
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty(self.observation_ref.value, "observation_ref")
        _require_non_empty(self.source_unit_ref.value, "source_unit_ref")
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.stage_run_id, "stage_run_id")
        _require_non_empty(self.work_item_id, "work_item_id")
        _require_non_empty(self.work_item_attempt_id, "work_item_attempt_id")
        _require_non_empty(self.llm_task_id, "llm_task_id")
        _require_non_empty(self.llm_attempt_id, "llm_attempt_id")
        _require_non_empty(self.prompt_id, "prompt_id")
        _require_non_empty(self.prompt_version, "prompt_version")
        _require_non_empty(self.raw_artifact_ref.value, "raw_artifact_ref")
        _require_non_empty(self.parsed_artifact_ref.value, "parsed_artifact_ref")
        if self.claim_index < 0:
            raise InvalidDraftClaimObservationProvenanceCandidate(
                "claim_index must be >= 0",
            )
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise InvalidDraftClaimObservationProvenanceCandidate(
                "created_at must be timezone-aware",
            )


class DraftClaimObservationProvenanceCandidateBuilder:
    def build(
        self,
        *,
        parsed_artifact: PipelineArtifact,
        source_unit_ref: SourceUnitRef,
        observations: tuple[DraftClaimObservation, ...],
        created_at: datetime,
    ) -> tuple[DraftClaimObservationProvenanceCandidate, ...]:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise InvalidDraftClaimObservationProvenanceCandidate(
                "created_at must be timezone-aware",
            )

        provenance = _provenance(parsed_artifact.payload.value)
        if provenance.source_unit_ref != source_unit_ref:
            raise InvalidDraftClaimObservationProvenanceCandidate(
                "source_unit_ref must match parsed artifact provenance",
            )

        raw_artifact_ref = _raw_artifact_ref(parsed_artifact)
        candidates: list[DraftClaimObservationProvenanceCandidate] = []
        for claim_index, observation in enumerate(observations):
            if observation.source_unit_ref != source_unit_ref:
                raise InvalidDraftClaimObservationProvenanceCandidate(
                    "observation source_unit_ref must match command source_unit_ref",
                )
            candidates.append(
                DraftClaimObservationProvenanceCandidate(
                    observation_ref=observation.observation_ref,
                    source_unit_ref=observation.source_unit_ref,
                    workflow_run_id=provenance.workflow_run_id,
                    stage_run_id=provenance.stage_run_id,
                    work_item_id=provenance.work_item_id,
                    work_item_attempt_id=provenance.work_item_attempt_id,
                    llm_task_id=provenance.llm_task_id,
                    llm_attempt_id=provenance.llm_attempt_id,
                    prompt_id=provenance.prompt_id,
                    prompt_version=provenance.prompt_version,
                    raw_artifact_ref=raw_artifact_ref,
                    parsed_artifact_ref=parsed_artifact.artifact_ref,
                    claim_index=claim_index,
                    created_at=created_at,
                )
            )
        return tuple(candidates)


def _provenance(
    payload: Mapping[str, JsonInputValue],
) -> ClaimExtractionArtifactProvenance:
    try:
        return ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields(
            payload,
        )
    except InvalidClaimExtractionArtifactProvenance as exc:
        raise InvalidDraftClaimObservationProvenanceCandidate(str(exc)) from exc


def _raw_artifact_ref(parsed_artifact: PipelineArtifact) -> ArtifactRef:
    payload = parsed_artifact.payload.value
    raw_ref_value = payload.get("raw_artifact_ref")
    if not isinstance(raw_ref_value, str) or not raw_ref_value.strip():
        raise InvalidDraftClaimObservationProvenanceCandidate(
            "raw_artifact_ref must be a non-empty string",
        )
    raw_artifact_ref = ArtifactRef(raw_ref_value)
    parent_refs = parsed_artifact.lineage.parent_refs
    if not parent_refs:
        raise InvalidDraftClaimObservationProvenanceCandidate(
            "parsed artifact lineage must contain raw_artifact_ref",
        )
    if raw_artifact_ref not in parent_refs:
        raise InvalidDraftClaimObservationProvenanceCandidate(
            "raw_artifact_ref must match parsed artifact lineage",
        )
    return raw_artifact_ref


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise InvalidDraftClaimObservationProvenanceCandidate(
            f"{field_name} must be non-empty",
        )
