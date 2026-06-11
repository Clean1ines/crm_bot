from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
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
    InvalidClaimExtractionDispatchArtifactProvenance,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_dispatch_prompt_a_artifact_factory import (
    DISPATCH_PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    DISPATCH_PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    ClaimExtractionDispatchPromptAArtifactFactory,
    ClaimExtractionDispatchPromptAArtifacts,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


def _created_at() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _updated_at() -> datetime:
    return datetime(2026, 6, 11, 12, 1, tzinfo=UTC)


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


def _claim() -> Mapping[str, object]:
    return {
        "claim": "Product turns documents into knowledge.",
        "granularity": "atomic",
        "possible_questions": ["What does the product do?"],
        "exclusion_scope": "",
        "evidence_block": "turns documents into knowledge",
    }


def _artifacts() -> ClaimExtractionDispatchPromptAArtifacts:
    return ClaimExtractionDispatchPromptAArtifactFactory().build(
        provenance=_provenance(),
        raw_output='{ "claims": [] }',
        parsed_claims_payload=(_claim(),),
        created_at=_created_at(),
        updated_at=_updated_at(),
    )


def _plain(value: object) -> object:
    if isinstance(value, MappingProxyType | Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    return value


def test_builds_raw_and_parsed_artifacts() -> None:
    artifacts = _artifacts()

    assert isinstance(artifacts, ClaimExtractionDispatchPromptAArtifacts)
    assert artifacts.raw_output_artifact.created_at == _created_at()
    assert artifacts.raw_output_artifact.updated_at == _updated_at()
    assert artifacts.parsed_output_artifact.created_at == _created_at()
    assert artifacts.parsed_output_artifact.updated_at == _updated_at()


def test_raw_artifact_kind_and_storage_attributes() -> None:
    raw_artifact = _artifacts().raw_output_artifact

    assert raw_artifact.artifact_kind == ArtifactKind(
        "knowledge_workbench.claim_observations.raw",
    )
    assert raw_artifact.artifact_kind == (
        DISPATCH_PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND
    )
    assert raw_artifact.status == ArtifactStatus.STORED
    assert raw_artifact.visibility == ArtifactVisibility.INTERNAL
    assert raw_artifact.retention_policy == RetentionPolicy.temporary()


def test_parsed_artifact_kind_and_storage_attributes() -> None:
    parsed_artifact = _artifacts().parsed_output_artifact

    assert parsed_artifact.artifact_kind == ArtifactKind(
        "knowledge_workbench.claim_observations.parsed",
    )
    assert parsed_artifact.artifact_kind == (
        DISPATCH_PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND
    )
    assert parsed_artifact.status == ArtifactStatus.VALIDATED
    assert parsed_artifact.visibility == ArtifactVisibility.INTERNAL
    assert parsed_artifact.retention_policy == RetentionPolicy.temporary()


def test_raw_artifact_payload_contains_dispatch_provenance_and_raw_output() -> None:
    payload = _plain(_artifacts().raw_output_artifact.payload.value)

    assert payload == {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "draft_observation_extraction",
        "source_unit_ref": "document-1.unit.0",
        "work_item_id": "work-item-1",
        "work_item_attempt_id": "attempt-1",
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
        "raw_output": '{ "claims": [] }',
    }


def test_parsed_artifact_payload_contains_dispatch_provenance_raw_ref_and_claims() -> (
    None
):
    artifacts = _artifacts()
    payload = _plain(artifacts.parsed_output_artifact.payload.value)

    assert payload == {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "draft_observation_extraction",
        "source_unit_ref": "document-1.unit.0",
        "work_item_id": "work-item-1",
        "work_item_attempt_id": "attempt-1",
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
        "raw_artifact_ref": artifacts.raw_output_artifact.artifact_ref.value,
        "claims": [dict(_claim())],
    }


def test_parsed_artifact_lineage_points_to_raw_artifact() -> None:
    artifacts = _artifacts()

    assert artifacts.parsed_output_artifact.lineage.parent_refs == (
        artifacts.raw_output_artifact.artifact_ref,
    )


def test_artifact_refs_are_deterministic_and_include_work_item_attempt_id() -> None:
    artifacts = _artifacts()

    assert artifacts.raw_output_artifact.artifact_ref == ArtifactRef(
        "claim-extraction-dispatch:workflow-1:draft_observation_extraction:"
        "work-item-1:attempt-1:raw",
    )
    assert artifacts.parsed_output_artifact.artifact_ref == ArtifactRef(
        "claim-extraction-dispatch:workflow-1:draft_observation_extraction:"
        "work-item-1:attempt-1:parsed",
    )
    assert "attempt-1" in artifacts.raw_output_artifact.artifact_ref.value
    assert "task_id" not in artifacts.raw_output_artifact.artifact_ref.value
    assert "attempt_id" not in artifacts.raw_output_artifact.artifact_ref.value


def test_naive_created_at_rejected() -> None:
    with pytest.raises(ValueError, match="created_at"):
        ClaimExtractionDispatchPromptAArtifactFactory().build(
            provenance=_provenance(),
            raw_output='{ "claims": [] }',
            parsed_claims_payload=(_claim(),),
            created_at=datetime(2026, 6, 11, 12, 0),
            updated_at=_updated_at(),
        )


def test_naive_updated_at_rejected() -> None:
    with pytest.raises(ValueError, match="updated_at"):
        ClaimExtractionDispatchPromptAArtifactFactory().build(
            provenance=_provenance(),
            raw_output='{ "claims": [] }',
            parsed_claims_payload=(_claim(),),
            created_at=_created_at(),
            updated_at=datetime(2026, 6, 11, 12, 1),
        )


def test_empty_raw_output_rejected_by_provenance_payload_contract() -> None:
    with pytest.raises(
        InvalidClaimExtractionDispatchArtifactProvenance,
        match="raw_output",
    ):
        ClaimExtractionDispatchPromptAArtifactFactory().build(
            provenance=_provenance(),
            raw_output=" ",
            parsed_claims_payload=(_claim(),),
            created_at=_created_at(),
            updated_at=_updated_at(),
        )


def test_claims_must_be_tuple_of_mappings() -> None:
    with pytest.raises(
        InvalidClaimExtractionDispatchArtifactProvenance,
        match="claims must be a tuple",
    ):
        ClaimExtractionDispatchPromptAArtifactFactory().build(
            provenance=_provenance(),
            raw_output='{ "claims": [] }',
            parsed_claims_payload=[_claim()],
            created_at=_created_at(),
            updated_at=_updated_at(),
        )
