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
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    JsonInputValue,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_artifact_provenance import (
    PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES,
    PROVENANCE_PAYLOAD_FIELD_NAMES,
    ClaimExtractionArtifactProvenance,
    InvalidClaimExtractionArtifactProvenance,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_text import (
    DraftClaimText,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.evidence_block import (
    EvidenceBlock,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.exclusion_scope import (
    ExclusionScope,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.possible_question import (
    PossibleQuestion,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND = ArtifactKind(
    "knowledge_workbench.claim_observations.parsed"
)
_LEGACY_TOP_LEVEL_FIELDS = frozenset({"claims"})
_PROVENANCE_TOP_LEVEL_FIELDS = frozenset(PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES)
_CLAIM_FIELDS = frozenset(
    {
        "claim",
        "granularity",
        "possible_questions",
        "exclusion_scope",
        "evidence_block",
    }
)


class InvalidDraftClaimObservationArtifact(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DraftClaimObservationArtifactParserInput:
    artifact: PipelineArtifact
    source_unit_ref: SourceUnitRef
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


class DraftClaimObservationArtifactParser:
    def parse(
        self,
        input: DraftClaimObservationArtifactParserInput,
    ) -> tuple[DraftClaimObservation, ...]:
        artifact = input.artifact

        if artifact.artifact_kind != EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND:
            raise InvalidDraftClaimObservationArtifact("wrong artifact kind")

        payload = artifact.payload.value
        self._validate_top_level_payload(payload)
        claims_value = payload["claims"]
        if not isinstance(claims_value, (list, tuple)):
            raise InvalidDraftClaimObservationArtifact("claims must be a list or tuple")

        observations: list[DraftClaimObservation] = []
        for index, claim_value in enumerate(claims_value):
            claim_mapping = self._claim_mapping(claim_value)
            observations.append(
                self._build_observation(
                    artifact=artifact,
                    source_unit_ref=input.source_unit_ref,
                    created_at=input.created_at,
                    index=index,
                    claim_mapping=claim_mapping,
                )
            )

        return tuple(observations)

    def _validate_top_level_payload(
        self,
        payload: Mapping[str, JsonInputValue],
    ) -> None:
        payload_fields = set(payload.keys())
        if payload_fields == _LEGACY_TOP_LEVEL_FIELDS:
            return
        if payload_fields != _PROVENANCE_TOP_LEVEL_FIELDS:
            raise InvalidDraftClaimObservationArtifact(
                "payload must contain claims only or the full Prompt A provenance payload"
            )
        try:
            ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields(payload)
        except InvalidClaimExtractionArtifactProvenance as exc:
            raise InvalidDraftClaimObservationArtifact(str(exc)) from exc

    def _claim_mapping(
        self,
        claim_value: JsonInputValue,
    ) -> Mapping[str, JsonInputValue]:
        if not isinstance(claim_value, Mapping):
            raise InvalidDraftClaimObservationArtifact("claim item must be an object")

        claim_fields = set(claim_value.keys())

        if claim_fields != _CLAIM_FIELDS:
            raise InvalidDraftClaimObservationArtifact(
                "claim object must contain exactly Prompt A draft claim fields"
            )

        for field_name, field_value in claim_value.items():
            if field_value is None:
                raise InvalidDraftClaimObservationArtifact(
                    f"claim field {field_name} must not be null"
                )

        return claim_value

    def _build_observation(
        self,
        *,
        artifact: PipelineArtifact,
        source_unit_ref: SourceUnitRef,
        created_at: datetime,
        index: int,
        claim_mapping: Mapping[str, JsonInputValue],
    ) -> DraftClaimObservation:
        claim = self._required_string(claim_mapping, "claim")
        granularity = self._granularity(claim_mapping)
        possible_questions = self._possible_questions(claim_mapping)
        exclusion_scope = self._required_string(claim_mapping, "exclusion_scope")
        evidence_block = self._required_string(claim_mapping, "evidence_block")

        try:
            return DraftClaimObservation(
                observation_ref=DraftClaimObservationRef(
                    f"{artifact.artifact_ref.value}:draft-claim:{index}"
                ),
                source_unit_ref=source_unit_ref,
                claim=DraftClaimText(claim),
                granularity=granularity,
                possible_questions=possible_questions,
                exclusion_scope=ExclusionScope(exclusion_scope),
                evidence_block=EvidenceBlock(evidence_block),
                created_at=created_at,
            )
        except ValueError as exc:
            raise InvalidDraftClaimObservationArtifact(str(exc)) from exc

    def _required_string(
        self,
        claim_mapping: Mapping[str, JsonInputValue],
        field_name: str,
    ) -> str:
        value = claim_mapping[field_name]
        if not isinstance(value, str):
            raise InvalidDraftClaimObservationArtifact(
                f"claim field {field_name} must be a string"
            )
        return value

    def _granularity(
        self,
        claim_mapping: Mapping[str, JsonInputValue],
    ) -> DraftClaimGranularity:
        value = self._required_string(claim_mapping, "granularity")
        try:
            return DraftClaimGranularity(value)
        except ValueError as exc:
            raise InvalidDraftClaimObservationArtifact(
                "granularity must be atomic or composite"
            ) from exc

    def _possible_questions(
        self,
        claim_mapping: Mapping[str, JsonInputValue],
    ) -> tuple[PossibleQuestion, ...]:
        value = claim_mapping["possible_questions"]
        if not isinstance(value, (list, tuple)):
            raise InvalidDraftClaimObservationArtifact(
                "possible_questions must be a list or tuple"
            )

        questions: list[PossibleQuestion] = []
        for question_value in value:
            if not isinstance(question_value, str):
                raise InvalidDraftClaimObservationArtifact(
                    "possible_questions must contain only strings"
                )
            try:
                questions.append(PossibleQuestion(question_value))
            except ValueError as exc:
                raise InvalidDraftClaimObservationArtifact(str(exc)) from exc

        return tuple(questions)
