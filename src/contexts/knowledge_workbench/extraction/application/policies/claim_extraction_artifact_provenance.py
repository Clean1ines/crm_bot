from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self, TypeAlias

from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import JsonInputValue
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import SourceUnitRef

ClaimExtractionProvenancePayloadFields: TypeAlias = dict[str, str]
ClaimExtractionArtifactPayloadFields: TypeAlias = dict[str, JsonInputValue]

PROVENANCE_PAYLOAD_FIELD_NAMES = (
    "workflow_run_id",
    "stage_run_id",
    "source_unit_ref",
    "work_item_id",
    "work_item_attempt_id",
    "llm_task_id",
    "llm_attempt_id",
    "prompt_id",
    "prompt_version",
)
RAW_ARTIFACT_PAYLOAD_FIELD_NAMES = PROVENANCE_PAYLOAD_FIELD_NAMES + ("raw_output",)
PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES = PROVENANCE_PAYLOAD_FIELD_NAMES + (
    "raw_artifact_ref",
    "claims",
)


class InvalidClaimExtractionArtifactProvenance(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ClaimExtractionArtifactProvenance:
    workflow_run_id: str
    stage_run_id: str
    source_unit_ref: SourceUnitRef
    work_item_id: str
    work_item_attempt_id: str
    llm_task_id: str
    llm_attempt_id: str
    prompt_id: str
    prompt_version: str

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.stage_run_id, "stage_run_id")
        _require_non_empty(self.source_unit_ref.value, "source_unit_ref")
        _require_non_empty(self.work_item_id, "work_item_id")
        _require_non_empty(self.work_item_attempt_id, "work_item_attempt_id")
        _require_non_empty(self.llm_task_id, "llm_task_id")
        _require_non_empty(self.llm_attempt_id, "llm_attempt_id")
        _require_non_empty(self.prompt_id, "prompt_id")
        _require_non_empty(self.prompt_version, "prompt_version")

    def to_payload_fields(self) -> ClaimExtractionProvenancePayloadFields:
        return {
            "workflow_run_id": self.workflow_run_id,
            "stage_run_id": self.stage_run_id,
            "source_unit_ref": self.source_unit_ref.value,
            "work_item_id": self.work_item_id,
            "work_item_attempt_id": self.work_item_attempt_id,
            "llm_task_id": self.llm_task_id,
            "llm_attempt_id": self.llm_attempt_id,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
        }

    def to_raw_artifact_payload_fields(self, *, raw_output: str) -> ClaimExtractionArtifactPayloadFields:
        _require_non_empty(raw_output, "raw_output")
        payload: ClaimExtractionArtifactPayloadFields = dict(self.to_payload_fields())
        payload["raw_output"] = raw_output
        return payload

    def to_parsed_artifact_payload_fields(
        self,
        *,
        raw_artifact_ref: ArtifactRef,
        claims: tuple[Mapping[str, JsonInputValue], ...],
    ) -> ClaimExtractionArtifactPayloadFields:
        _require_non_empty(raw_artifact_ref.value, "raw_artifact_ref")
        _require_claims_tuple(claims)
        payload: ClaimExtractionArtifactPayloadFields = dict(self.to_payload_fields())
        payload["raw_artifact_ref"] = raw_artifact_ref.value
        payload["claims"] = claims
        return payload

    @classmethod
    def from_payload_fields(cls, payload: Mapping[str, JsonInputValue]) -> Self:
        return cls(
            workflow_run_id=_required_payload_str(payload, "workflow_run_id"),
            stage_run_id=_required_payload_str(payload, "stage_run_id"),
            source_unit_ref=SourceUnitRef(_required_payload_str(payload, "source_unit_ref")),
            work_item_id=_required_payload_str(payload, "work_item_id"),
            work_item_attempt_id=_required_payload_str(payload, "work_item_attempt_id"),
            llm_task_id=_required_payload_str(payload, "llm_task_id"),
            llm_attempt_id=_required_payload_str(payload, "llm_attempt_id"),
            prompt_id=_required_payload_str(payload, "prompt_id"),
            prompt_version=_required_payload_str(payload, "prompt_version"),
        )

    @classmethod
    def from_raw_artifact_payload_fields(cls, payload: Mapping[str, JsonInputValue]) -> Self:
        _required_payload_str(payload, "raw_output")
        return cls.from_payload_fields(payload)

    @classmethod
    def from_parsed_artifact_payload_fields(cls, payload: Mapping[str, JsonInputValue]) -> Self:
        _required_payload_str(payload, "raw_artifact_ref")
        _required_payload_claims(payload)
        return cls.from_payload_fields(payload)


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise InvalidClaimExtractionArtifactProvenance(f"{field_name} must be non-empty")


def _required_payload_str(payload: Mapping[str, JsonInputValue], field_name: str) -> str:
    if field_name not in payload:
        raise InvalidClaimExtractionArtifactProvenance(f"{field_name} is required")
    value = payload[field_name]
    if not isinstance(value, str) or not value.strip():
        raise InvalidClaimExtractionArtifactProvenance(
            f"{field_name} must be a non-empty string",
        )
    return value


def _required_payload_claims(payload: Mapping[str, JsonInputValue]) -> None:
    if "claims" not in payload:
        raise InvalidClaimExtractionArtifactProvenance("claims is required")
    value = payload["claims"]
    if not isinstance(value, (list, tuple)):
        raise InvalidClaimExtractionArtifactProvenance("claims must be a list or tuple")
    for claim in value:
        if not isinstance(claim, Mapping):
            raise InvalidClaimExtractionArtifactProvenance("claims must contain only objects")


def _require_claims_tuple(claims: tuple[Mapping[str, JsonInputValue], ...]) -> None:
    if not isinstance(claims, tuple):
        raise InvalidClaimExtractionArtifactProvenance("claims must be a tuple")
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise InvalidClaimExtractionArtifactProvenance("claims must contain only objects")
