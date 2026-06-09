from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

import pytest

from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    JsonInputValue,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_artifact_provenance import (
    PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES,
    PROVENANCE_PAYLOAD_FIELD_NAMES,
    RAW_ARTIFACT_PAYLOAD_FIELD_NAMES,
    ClaimExtractionArtifactProvenance,
    InvalidClaimExtractionArtifactProvenance,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


def _provenance() -> ClaimExtractionArtifactProvenance:
    return ClaimExtractionArtifactProvenance(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        work_item_id="work-item-1",
        work_item_attempt_id="work-attempt-1",
        llm_task_id="llm-task-1",
        llm_attempt_id="llm-attempt-1",
        prompt_id="prompt-a",
        prompt_version="v1",
    )


def _claim() -> Mapping[str, JsonInputValue]:
    return {
        "claim": "Product turns documents into knowledge.",
        "granularity": "atomic",
        "possible_questions": ("What does the product do?",),
        "exclusion_scope": "",
        "evidence_block": "turns documents into knowledge",
    }


def test_valid_provenance_accepts_all_required_fields() -> None:
    provenance = _provenance()

    assert provenance.workflow_run_id == "workflow-1"
    assert provenance.stage_run_id == "stage-1"
    assert provenance.source_unit_ref == SourceUnitRef("document-1.unit.0")
    assert provenance.work_item_id == "work-item-1"
    assert provenance.work_item_attempt_id == "work-attempt-1"
    assert provenance.llm_task_id == "llm-task-1"
    assert provenance.llm_attempt_id == "llm-attempt-1"
    assert provenance.prompt_id == "prompt-a"
    assert provenance.prompt_version == "v1"


@pytest.mark.parametrize(
    "field_name",
    (
        "workflow_run_id",
        "stage_run_id",
        "work_item_id",
        "work_item_attempt_id",
        "llm_task_id",
        "llm_attempt_id",
        "prompt_id",
        "prompt_version",
    ),
)
def test_empty_string_field_rejected(field_name: str) -> None:
    with pytest.raises(
        InvalidClaimExtractionArtifactProvenance,
        match=f"{field_name} must be non-empty",
    ):
        replace(_provenance(), **{field_name: " "})


def test_payload_fields_expose_string_values_not_domain_objects() -> None:
    fields = _provenance().to_payload_fields()

    assert set(fields) == set(PROVENANCE_PAYLOAD_FIELD_NAMES)
    assert fields == {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "stage-1",
        "source_unit_ref": "document-1.unit.0",
        "work_item_id": "work-item-1",
        "work_item_attempt_id": "work-attempt-1",
        "llm_task_id": "llm-task-1",
        "llm_attempt_id": "llm-attempt-1",
        "prompt_id": "prompt-a",
        "prompt_version": "v1",
    }
    assert all(isinstance(value, str) for value in fields.values())


def test_raw_artifact_payload_fields_include_provenance_and_raw_output() -> None:
    payload = _provenance().to_raw_artifact_payload_fields(
        raw_output='{ "claims": [] }',
    )

    assert set(payload) == set(RAW_ARTIFACT_PAYLOAD_FIELD_NAMES)
    assert payload["workflow_run_id"] == "workflow-1"
    assert payload["source_unit_ref"] == "document-1.unit.0"
    assert payload["raw_output"] == '{ "claims": [] }'


def test_raw_artifact_payload_rejects_empty_raw_output() -> None:
    with pytest.raises(
        InvalidClaimExtractionArtifactProvenance,
        match="raw_output must be non-empty",
    ):
        _provenance().to_raw_artifact_payload_fields(raw_output=" ")


def test_parsed_artifact_payload_fields_include_provenance_raw_ref_and_claims() -> None:
    payload = _provenance().to_parsed_artifact_payload_fields(
        raw_artifact_ref=ArtifactRef("raw-artifact-1"),
        claims=(_claim(),),
    )

    assert set(payload) == set(PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES)
    assert payload["workflow_run_id"] == "workflow-1"
    assert payload["source_unit_ref"] == "document-1.unit.0"
    assert payload["raw_artifact_ref"] == "raw-artifact-1"
    assert payload["claims"] == (_claim(),)


def test_parsed_artifact_provenance_can_be_extracted_from_payload_fields() -> None:
    payload = _provenance().to_parsed_artifact_payload_fields(
        raw_artifact_ref=ArtifactRef("raw-artifact-1"),
        claims=(_claim(),),
    )

    extracted = ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields(
        payload,
    )

    assert extracted == _provenance()


def test_missing_required_payload_field_rejected() -> None:
    payload = _provenance().to_parsed_artifact_payload_fields(
        raw_artifact_ref=ArtifactRef("raw-artifact-1"),
        claims=(_claim(),),
    )
    del payload["llm_attempt_id"]

    with pytest.raises(
        InvalidClaimExtractionArtifactProvenance,
        match="llm_attempt_id is required",
    ):
        ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields(payload)


def test_wrong_type_payload_field_rejected() -> None:
    payload = _provenance().to_parsed_artifact_payload_fields(
        raw_artifact_ref=ArtifactRef("raw-artifact-1"),
        claims=(_claim(),),
    )
    payload["prompt_version"] = 2

    with pytest.raises(
        InvalidClaimExtractionArtifactProvenance,
        match="prompt_version must be a non-empty string",
    ):
        ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields(payload)


def test_missing_claims_rejected_when_extracting_parsed_artifact_provenance() -> None:
    payload = _provenance().to_payload_fields()
    payload["raw_artifact_ref"] = "raw-artifact-1"

    with pytest.raises(
        InvalidClaimExtractionArtifactProvenance,
        match="claims is required",
    ):
        ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields(payload)


def test_claims_must_be_array_when_extracting_parsed_artifact_provenance() -> None:
    payload = _provenance().to_payload_fields()
    payload["raw_artifact_ref"] = "raw-artifact-1"
    payload["claims"] = "not-array"

    with pytest.raises(
        InvalidClaimExtractionArtifactProvenance,
        match="claims must be a list or tuple",
    ):
        ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields(payload)
