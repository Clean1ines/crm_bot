from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self, TypeAlias

from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    JsonInputValue,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.llm_runtime.application.results.llm_dispatch_output_artifact_payload import (
    LlmDispatchOutputArtifactPayload,
)


DispatchProvenancePayloadFields: TypeAlias = dict[str, str]
DispatchArtifactPayloadFields: TypeAlias = dict[str, JsonInputValue]

DISPATCH_PROVENANCE_PAYLOAD_FIELD_NAMES = (
    "workflow_run_id",
    "stage_run_id",
    "source_unit_ref",
    "work_item_id",
    "work_item_attempt_id",
    "prompt_id",
    "prompt_version",
)
DISPATCH_RAW_ARTIFACT_PAYLOAD_FIELD_NAMES = DISPATCH_PROVENANCE_PAYLOAD_FIELD_NAMES + (
    "raw_output",
)
DISPATCH_PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES = (
    DISPATCH_PROVENANCE_PAYLOAD_FIELD_NAMES
    + (
        "raw_artifact_ref",
        "claims",
    )
)


class InvalidClaimExtractionDispatchArtifactProvenance(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ClaimExtractionDispatchArtifactProvenance:
    workflow_run_id: str
    stage_run_id: str
    source_unit_ref: SourceUnitRef
    work_item_id: str
    work_item_attempt_id: str
    prompt_id: str
    prompt_version: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.stage_run_id, "stage_run_id")
        _require_non_empty_text(self.source_unit_ref.value, "source_unit_ref")
        _require_non_empty_text(self.work_item_id, "work_item_id")
        _require_non_empty_text(self.work_item_attempt_id, "work_item_attempt_id")
        _require_non_empty_text(self.prompt_id, "prompt_id")
        _require_non_empty_text(self.prompt_version, "prompt_version")

    @classmethod
    def from_llm_dispatch_output_payload(
        cls,
        payload: LlmDispatchOutputArtifactPayload,
    ) -> Self:
        if not isinstance(payload, LlmDispatchOutputArtifactPayload):
            raise TypeError("payload must be LlmDispatchOutputArtifactPayload")

        seed = payload.prompt_a_provenance_seed()
        work_item_id = _required_seed_text(seed, "work_item_id")
        if work_item_id != payload.work_item_id:
            raise InvalidClaimExtractionDispatchArtifactProvenance(
                "work_item_id must match dispatch output payload",
            )

        return cls(
            workflow_run_id=_required_seed_text(seed, "workflow_run_id"),
            stage_run_id=_required_seed_text(seed, "stage_run_id"),
            source_unit_ref=SourceUnitRef(_required_seed_text(seed, "source_unit_ref")),
            work_item_id=work_item_id,
            work_item_attempt_id=payload.attempt_id,
            prompt_id=_required_seed_text(seed, "prompt_id"),
            prompt_version=_required_seed_text(seed, "prompt_version"),
        )

    def to_payload_fields(self) -> DispatchProvenancePayloadFields:
        return {
            "workflow_run_id": self.workflow_run_id,
            "stage_run_id": self.stage_run_id,
            "source_unit_ref": self.source_unit_ref.value,
            "work_item_id": self.work_item_id,
            "work_item_attempt_id": self.work_item_attempt_id,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
        }

    def to_raw_artifact_payload_fields(
        self,
        *,
        raw_output: str,
    ) -> DispatchArtifactPayloadFields:
        _require_non_empty_text(raw_output, "raw_output")
        payload = self._json_payload_fields()
        payload["raw_output"] = raw_output
        return payload

    def to_parsed_artifact_payload_fields(
        self,
        *,
        raw_artifact_ref: ArtifactRef,
        claims: tuple[Mapping[str, JsonInputValue], ...],
    ) -> DispatchArtifactPayloadFields:
        _require_non_empty_text(raw_artifact_ref.value, "raw_artifact_ref")
        _require_claims_tuple(claims)

        payload = self._json_payload_fields()
        payload["raw_artifact_ref"] = raw_artifact_ref.value
        payload["claims"] = [dict(claim) for claim in claims]
        return payload

    @classmethod
    def from_payload_fields(
        cls,
        payload: Mapping[str, JsonInputValue],
    ) -> Self:
        return cls(
            workflow_run_id=_required_payload_text(payload, "workflow_run_id"),
            stage_run_id=_required_payload_text(payload, "stage_run_id"),
            source_unit_ref=SourceUnitRef(
                _required_payload_text(payload, "source_unit_ref"),
            ),
            work_item_id=_required_payload_text(payload, "work_item_id"),
            work_item_attempt_id=_required_payload_text(
                payload,
                "work_item_attempt_id",
            ),
            prompt_id=_required_payload_text(payload, "prompt_id"),
            prompt_version=_required_payload_text(payload, "prompt_version"),
        )

    @classmethod
    def from_raw_artifact_payload_fields(
        cls,
        payload: Mapping[str, JsonInputValue],
    ) -> Self:
        _required_payload_text(payload, "raw_output")
        return cls.from_payload_fields(payload)

    @classmethod
    def from_parsed_artifact_payload_fields(
        cls,
        payload: Mapping[str, JsonInputValue],
    ) -> Self:
        _required_payload_text(payload, "raw_artifact_ref")
        _required_payload_claims(payload)
        return cls.from_payload_fields(payload)

    def _json_payload_fields(self) -> DispatchArtifactPayloadFields:
        payload: DispatchArtifactPayloadFields = {}
        for key, value in self.to_payload_fields().items():
            payload[key] = value
        return payload


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidClaimExtractionDispatchArtifactProvenance(
            f"{field_name} must be non-empty",
        )


def _required_seed_text(payload: Mapping[str, object], field_name: str) -> str:
    if field_name not in payload:
        raise InvalidClaimExtractionDispatchArtifactProvenance(
            f"{field_name} is required",
        )
    value = payload[field_name]
    if not isinstance(value, str) or not value.strip():
        raise InvalidClaimExtractionDispatchArtifactProvenance(
            f"{field_name} must be a non-empty string",
        )
    return value


def _required_payload_text(
    payload: Mapping[str, JsonInputValue],
    field_name: str,
) -> str:
    if field_name not in payload:
        raise InvalidClaimExtractionDispatchArtifactProvenance(
            f"{field_name} is required",
        )
    value = payload[field_name]
    if not isinstance(value, str) or not value.strip():
        raise InvalidClaimExtractionDispatchArtifactProvenance(
            f"{field_name} must be a non-empty string",
        )
    return value


def _required_payload_claims(payload: Mapping[str, JsonInputValue]) -> None:
    if "claims" not in payload:
        raise InvalidClaimExtractionDispatchArtifactProvenance("claims is required")
    value = payload["claims"]
    if not isinstance(value, list | tuple):
        raise InvalidClaimExtractionDispatchArtifactProvenance(
            "claims must be a list or tuple",
        )
    for claim in value:
        if not isinstance(claim, Mapping):
            raise InvalidClaimExtractionDispatchArtifactProvenance(
                "claims must contain only objects",
            )


def _require_claims_tuple(
    claims: tuple[Mapping[str, JsonInputValue], ...],
) -> None:
    if not isinstance(claims, tuple):
        raise InvalidClaimExtractionDispatchArtifactProvenance(
            "claims must be a tuple",
        )
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise InvalidClaimExtractionDispatchArtifactProvenance(
                "claims must contain only objects",
            )
