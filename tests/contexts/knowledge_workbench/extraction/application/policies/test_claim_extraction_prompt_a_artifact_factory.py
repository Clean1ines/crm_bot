from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

import pytest

from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
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
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_artifact_provenance import (
    ClaimExtractionArtifactProvenance,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_prompt_a_artifact_factory import (
    PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    ClaimExtractionPromptAArtifactFactory,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


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


def _artifacts():
    return ClaimExtractionPromptAArtifactFactory().build(
        provenance=_provenance(),
        raw_output='{ "claims": [] }',
        parsed_claims_payload=(_claim(),),
        created_at=_now(),
        updated_at=_now(),
    )


def test_factory_builds_raw_artifact_with_expected_kind() -> None:
    artifacts = _artifacts()

    raw = artifacts.raw_output_artifact
    assert raw.artifact_kind == PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND
    assert raw.artifact_ref == ArtifactRef(
        "claim-extraction:workflow-1:stage-1:work-item-1:work-attempt-1:llm-attempt-1:raw",
    )
    assert raw.status is ArtifactStatus.STORED
    assert raw.visibility is ArtifactVisibility.INTERNAL
    assert raw.retention_policy == RetentionPolicy.temporary()
    assert raw.lineage.parent_refs == ()


def test_raw_artifact_payload_contains_provenance_fields() -> None:
    raw = _artifacts().raw_output_artifact

    assert raw.payload.value["workflow_run_id"] == "workflow-1"
    assert raw.payload.value["stage_run_id"] == "stage-1"
    assert raw.payload.value["source_unit_ref"] == "document-1.unit.0"
    assert raw.payload.value["work_item_id"] == "work-item-1"
    assert raw.payload.value["work_item_attempt_id"] == "work-attempt-1"
    assert raw.payload.value["llm_task_id"] == "llm-task-1"
    assert raw.payload.value["llm_attempt_id"] == "llm-attempt-1"
    assert raw.payload.value["prompt_id"] == "prompt-a"
    assert raw.payload.value["prompt_version"] == "v1"
    assert raw.payload.value["raw_output"] == '{ "claims": [] }'


def test_factory_builds_parsed_artifact_with_expected_kind() -> None:
    artifacts = _artifacts()

    parsed = artifacts.parsed_output_artifact
    assert parsed.artifact_kind == PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND
    assert parsed.artifact_ref == ArtifactRef(
        "claim-extraction:workflow-1:stage-1:work-item-1:work-attempt-1:llm-attempt-1:parsed",
    )
    assert parsed.status is ArtifactStatus.VALIDATED
    assert parsed.visibility is ArtifactVisibility.INTERNAL
    assert parsed.retention_policy == RetentionPolicy.temporary()


def test_parsed_artifact_lineage_contains_raw_artifact_ref() -> None:
    artifacts = _artifacts()

    assert artifacts.parsed_output_artifact.lineage.parent_refs == (
        artifacts.raw_output_artifact.artifact_ref,
    )


def test_parsed_artifact_payload_contains_claims_and_provenance() -> None:
    parsed = _artifacts().parsed_output_artifact

    assert parsed.payload.value["claims"] == (_claim(),)
    assert parsed.payload.value["raw_artifact_ref"] == (
        "claim-extraction:workflow-1:stage-1:work-item-1:work-attempt-1:llm-attempt-1:raw"
    )
    assert parsed.payload.value["workflow_run_id"] == "workflow-1"
    assert parsed.payload.value["stage_run_id"] == "stage-1"
    assert parsed.payload.value["source_unit_ref"] == "document-1.unit.0"
    assert parsed.payload.value["work_item_id"] == "work-item-1"
    assert parsed.payload.value["work_item_attempt_id"] == "work-attempt-1"
    assert parsed.payload.value["llm_task_id"] == "llm-task-1"
    assert parsed.payload.value["llm_attempt_id"] == "llm-attempt-1"
    assert parsed.payload.value["prompt_id"] == "prompt-a"
    assert parsed.payload.value["prompt_version"] == "v1"


def test_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        ClaimExtractionPromptAArtifactFactory().build(
            provenance=_provenance(),
            raw_output='{ "claims": [] }',
            parsed_claims_payload=(_claim(),),
            created_at=datetime(2026, 6, 8, 12, 0),
            updated_at=_now(),
        )

    with pytest.raises(ValueError, match="updated_at must be timezone-aware"):
        ClaimExtractionPromptAArtifactFactory().build(
            provenance=_provenance(),
            raw_output='{ "claims": [] }',
            parsed_claims_payload=(_claim(),),
            created_at=_now(),
            updated_at=datetime(2026, 6, 8, 12, 0),
        )


def test_updated_at_cannot_be_before_created_at_via_pipeline_artifact_invariant() -> (
    None
):
    with pytest.raises(ValueError, match="updated_at must be >= created_at"):
        ClaimExtractionPromptAArtifactFactory().build(
            provenance=_provenance(),
            raw_output='{ "claims": [] }',
            parsed_claims_payload=(_claim(),),
            created_at=_now(),
            updated_at=datetime(2026, 6, 8, 11, 59, tzinfo=timezone.utc),
        )
