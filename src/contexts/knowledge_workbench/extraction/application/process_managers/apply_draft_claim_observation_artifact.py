from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_artifact_parser import (
    DraftClaimObservationArtifactParser,
    DraftClaimObservationArtifactParserInput,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import (
    DraftClaimObservationProvenanceCandidate,
    DraftClaimObservationProvenanceCandidateBuilder,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_application_unit_of_work_port import (
    DraftClaimObservationApplicationUnitOfWorkPort,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.events.draft_claim_observation_events import (
    DraftClaimObservationsApplied,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


@dataclass(frozen=True, slots=True)
class ApplyDraftClaimObservationArtifactCommand:
    parsed_artifact: PipelineArtifact
    source_unit_ref: SourceUnitRef
    created_at: datetime
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ApplyDraftClaimObservationArtifactResult:
    observations: tuple[DraftClaimObservation, ...]
    provenance_candidates: tuple[DraftClaimObservationProvenanceCandidate, ...]
    event: DraftClaimObservationsApplied


class ApplyDraftClaimObservationArtifact:
    def __init__(
        self,
        *,
        parser: DraftClaimObservationArtifactParser,
        unit_of_work: DraftClaimObservationApplicationUnitOfWorkPort,
        provenance_candidate_builder: DraftClaimObservationProvenanceCandidateBuilder | None = None,
    ) -> None:
        self._parser = parser
        self._unit_of_work = unit_of_work
        self._provenance_candidate_builder = (
            provenance_candidate_builder
            or DraftClaimObservationProvenanceCandidateBuilder()
        )

    def execute(
        self,
        command: ApplyDraftClaimObservationArtifactCommand,
    ) -> ApplyDraftClaimObservationArtifactResult:
        try:
            observations = self._parser.parse(
                DraftClaimObservationArtifactParserInput(
                    artifact=command.parsed_artifact,
                    source_unit_ref=command.source_unit_ref,
                    created_at=command.created_at,
                )
            )
            provenance_candidates = self._provenance_candidate_builder.build(
                parsed_artifact=command.parsed_artifact,
                source_unit_ref=command.source_unit_ref,
                observations=observations,
                created_at=command.created_at,
            )
            event = DraftClaimObservationsApplied(
                artifact_ref=command.parsed_artifact.artifact_ref,
                source_unit_ref=command.source_unit_ref,
                observation_count=len(observations),
                occurred_at=command.occurred_at,
            )

            self._unit_of_work.save_draft_claim_observations(observations)
            self._unit_of_work.save_draft_claim_observation_provenance_candidates(
                provenance_candidates,
            )
            self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return ApplyDraftClaimObservationArtifactResult(
            observations=observations,
            provenance_candidates=provenance_candidates,
            event=event,
        )
