from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

import pytest

from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    JsonInputValue,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_dispatch_artifact_provenance import (
    DISPATCH_PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES,
    DISPATCH_PROVENANCE_PAYLOAD_FIELD_NAMES,
    DISPATCH_RAW_ARTIFACT_PAYLOAD_FIELD_NAMES,
    ClaimExtractionDispatchArtifactProvenance,
    InvalidClaimExtractionDispatchArtifactProvenance,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.llm_runtime.application.results.llm_dispatch_output_artifact_payload import (
    LlmDispatchOutputArtifactPayload,
)


def _dispatch_payload(
    *,
    seed_override: Mapping[str, object] | None = None,
) -> dict[str, object]:
    seed: dict[str, object] = {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "draft_observation_extraction",
        "source_unit_ref": "document-1.unit.0",
        "work_item_id": "work-item-1",
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
    }
    if seed_override is not None:
        seed.update(seed_override)

    return {
        "work_item_id": "work-item-1",
        "schedule_payload": {
            "provider_messages": (
                {
                    "role": "user",
                    "content": "Extract facts",
                },
            ),
            "prompt_a_provenance": seed,
        },
    }


def _llm_dispatch_output_payload(
    *,
    dispatch_payload: Mapping[str, object] | None = None,
    work_item_id: str = "work-item-1",
) -> LlmDispatchOutputArtifactPayload:
    return LlmDispatchOutputArtifactPayload(
        attempt_id="attempt-1",
        work_item_id=work_item_id,
        attempt_number=1,
        worker_ref="worker-1",
        dispatch_payload=_dispatch_payload()
        if dispatch_payload is None
        else dispatch_payload,
        output_payload={"raw_text": '{"claims": []}'},
        finished_at="2026-06-11T12:01:00+00:00",
    )


def _provenance() -> ClaimExtractionDispatchArtifactProvenance:
    return ClaimExtractionDispatchArtifactProvenance(
        workflow_run_id="workflow-1",
        stage_run_id="draft_observation_extraction",
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        work_item_id="work-item-1",
        work_item_attempt_id="attempt-1",
        prompt_id="faq_claim_observations",
        prompt_version="v1",
    )


def _claim() -> Mapping[str, JsonInputValue]:
    return {
        "claim": "Product turns documents into knowledge.",
        "granularity": "atomic",
        "possible_questions": ["What does the product do?"],
        "exclusion_scope": "",
        "evidence_block": "turns documents into knowledge",
    }


def test_builds_provenance_from_llm_dispatch_output_payload() -> None:
    provenance = (
        ClaimExtractionDispatchArtifactProvenance.from_llm_dispatch_output_payload(
            _llm_dispatch_output_payload(),
        )
    )

    assert provenance == _provenance()


def test_work_item_attempt_id_is_dispatch_attempt_id() -> None:
    provenance = (
        ClaimExtractionDispatchArtifactProvenance.from_llm_dispatch_output_payload(
            _llm_dispatch_output_payload(),
        )
    )

    assert provenance.work_item_attempt_id == "attempt-1"


def test_seed_work_item_id_must_match_dispatch_payload_work_item_id() -> None:
    dispatch_payload = _dispatch_payload(
        seed_override={"work_item_id": "different-work-item"},
    )

    with pytest.raises(
        InvalidClaimExtractionDispatchArtifactProvenance,
        match="work_item_id must match",
    ):
        ClaimExtractionDispatchArtifactProvenance.from_llm_dispatch_output_payload(
            _llm_dispatch_output_payload(dispatch_payload=dispatch_payload),
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "workflow_run_id",
        "stage_run_id",
        "source_unit_ref",
        "prompt_id",
        "prompt_version",
    ),
)
def test_missing_seed_field_rejected(field_name: str) -> None:
    dispatch_payload = _dispatch_payload()
    schedule_payload = dict(dispatch_payload["schedule_payload"])
    seed = dict(schedule_payload["prompt_a_provenance"])
    del seed[field_name]
    schedule_payload["prompt_a_provenance"] = seed
    dispatch_payload["schedule_payload"] = schedule_payload

    with pytest.raises(
        InvalidClaimExtractionDispatchArtifactProvenance,
        match=f"{field_name} is required",
    ):
        ClaimExtractionDispatchArtifactProvenance.from_llm_dispatch_output_payload(
            _llm_dispatch_output_payload(dispatch_payload=dispatch_payload),
        )


def test_payload_fields_expose_dispatch_centric_string_values() -> None:
    fields = _provenance().to_payload_fields()

    assert set(fields) == set(DISPATCH_PROVENANCE_PAYLOAD_FIELD_NAMES)
    assert fields == {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "draft_observation_extraction",
        "source_unit_ref": "document-1.unit.0",
        "work_item_id": "work-item-1",
        "work_item_attempt_id": "attempt-1",
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
    }
    assert all(isinstance(value, str) for value in fields.values())


def test_raw_payload_fields_include_raw_output_without_old_ids() -> None:
    payload = _provenance().to_raw_artifact_payload_fields(
        raw_output='{ "claims": [] }',
    )

    assert set(payload) == set(DISPATCH_RAW_ARTIFACT_PAYLOAD_FIELD_NAMES)
    assert payload["workflow_run_id"] == "workflow-1"
    assert payload["source_unit_ref"] == "document-1.unit.0"
    assert payload["work_item_attempt_id"] == "attempt-1"
    assert payload["raw_output"] == '{ "claims": [] }'
    assert "task_id" not in payload
    assert "attempt_id" not in payload


def test_parsed_payload_fields_include_raw_ref_and_claims_without_old_ids() -> None:
    payload = _provenance().to_parsed_artifact_payload_fields(
        raw_artifact_ref=ArtifactRef("raw-artifact-1"),
        claims=(_claim(),),
    )

    assert set(payload) == set(DISPATCH_PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES)
    assert payload["workflow_run_id"] == "workflow-1"
    assert payload["source_unit_ref"] == "document-1.unit.0"
    assert payload["work_item_attempt_id"] == "attempt-1"
    assert payload["raw_artifact_ref"] == "raw-artifact-1"
    assert payload["claims"] == [dict(_claim())]
    assert "task_id" not in payload
    assert "attempt_id" not in payload


def test_from_parsed_artifact_payload_fields_round_trip() -> None:
    payload = _provenance().to_parsed_artifact_payload_fields(
        raw_artifact_ref=ArtifactRef("raw-artifact-1"),
        claims=(_claim(),),
    )

    extracted = (
        ClaimExtractionDispatchArtifactProvenance.from_parsed_artifact_payload_fields(
            payload,
        )
    )

    assert extracted == _provenance()


def test_from_raw_artifact_payload_fields_round_trip() -> None:
    payload = _provenance().to_raw_artifact_payload_fields(
        raw_output='{ "claims": [] }',
    )

    extracted = (
        ClaimExtractionDispatchArtifactProvenance.from_raw_artifact_payload_fields(
            payload,
        )
    )

    assert extracted == _provenance()


def test_empty_string_field_rejected() -> None:
    with pytest.raises(
        InvalidClaimExtractionDispatchArtifactProvenance,
        match="prompt_id must be non-empty",
    ):
        replace(_provenance(), prompt_id=" ")


def test_missing_claims_rejected_when_extracting_parsed_payload() -> None:
    payload = _provenance().to_payload_fields()
    payload["raw_artifact_ref"] = "raw-artifact-1"

    with pytest.raises(
        InvalidClaimExtractionDispatchArtifactProvenance,
        match="claims is required",
    ):
        ClaimExtractionDispatchArtifactProvenance.from_parsed_artifact_payload_fields(
            payload,
        )


@pytest.mark.parametrize(
    "claims",
    (
        "not-array",
        ("not-object",),
    ),
)
def test_claims_must_be_array_of_mappings_when_extracting_parsed_payload(
    claims: JsonInputValue,
) -> None:
    payload = _provenance().to_payload_fields()
    payload["raw_artifact_ref"] = "raw-artifact-1"
    payload["claims"] = claims

    with pytest.raises(
        InvalidClaimExtractionDispatchArtifactProvenance,
        match="claims",
    ):
        ClaimExtractionDispatchArtifactProvenance.from_parsed_artifact_payload_fields(
            payload,
        )
