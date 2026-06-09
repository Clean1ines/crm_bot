from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

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
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_artifact_parser import (
    EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    DraftClaimObservationArtifactParser,
    DraftClaimObservationArtifactParserInput,
    InvalidDraftClaimObservationArtifact,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


ROOT = Path(__file__).resolve().parents[6]
PARSER_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "policies"
    / "draft_claim_observation_artifact_parser.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _claim_payload(
    *,
    claim: JsonInputValue = "Product turns documents into knowledge.",
    granularity: JsonInputValue = "atomic",
    possible_questions: JsonInputValue = ("What does the product do?",),
    exclusion_scope: JsonInputValue = "Pricing is not covered.",
    evidence_block: JsonInputValue = "turns documents into knowledge",
) -> dict[str, JsonInputValue]:
    return {
        "claim": claim,
        "granularity": granularity,
        "possible_questions": possible_questions,
        "exclusion_scope": exclusion_scope,
        "evidence_block": evidence_block,
    }


def _provenance_payload(
    *,
    claims: JsonInputValue,
    raw_artifact_ref: JsonInputValue = "raw-artifact-1",
) -> dict[str, JsonInputValue]:
    return {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "stage-1",
        "source_unit_ref": "document-1.unit.0",
        "work_item_id": "work-item-1",
        "work_item_attempt_id": "work-attempt-1",
        "llm_task_id": "llm-task-1",
        "llm_attempt_id": "llm-attempt-1",
        "prompt_id": "prompt-a",
        "prompt_version": "v1",
        "raw_artifact_ref": raw_artifact_ref,
        "claims": claims,
    }


def _artifact(
    payload: dict[str, JsonInputValue],
    *,
    artifact_kind: ArtifactKind = EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    artifact_ref: ArtifactRef = ArtifactRef("artifact-1"),
) -> PipelineArtifact:
    return PipelineArtifact(
        artifact_ref=artifact_ref,
        artifact_kind=artifact_kind,
        payload=ArtifactPayload(payload),
        status=ArtifactStatus.VALIDATED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )


def _parse(
    payload: dict[str, JsonInputValue],
    *,
    artifact_kind: ArtifactKind = EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    artifact_ref: ArtifactRef = ArtifactRef("artifact-1"),
    source_unit_ref: SourceUnitRef = SourceUnitRef("document-1.unit.0"),
    created_at: datetime | None = None,
):
    return DraftClaimObservationArtifactParser().parse(
        DraftClaimObservationArtifactParserInput(
            artifact=_artifact(
                payload,
                artifact_kind=artifact_kind,
                artifact_ref=artifact_ref,
            ),
            source_unit_ref=source_unit_ref,
            created_at=created_at or _now(),
        )
    )


def test_parses_one_atomic_claim() -> None:
    observations = _parse({"claims": [_claim_payload()]})

    assert len(observations) == 1
    observation = observations[0]
    assert observation.claim.value == "Product turns documents into knowledge."
    assert observation.granularity is DraftClaimGranularity.ATOMIC
    assert tuple(question.value for question in observation.possible_questions) == (
        "What does the product do?",
    )
    assert observation.exclusion_scope.value == "Pricing is not covered."
    assert observation.evidence_block.value == "turns documents into knowledge"


def test_parses_one_composite_claim() -> None:
    observations = _parse(
        {
            "claims": [
                _claim_payload(
                    claim="Onboarding includes several steps.",
                    granularity="composite",
                    possible_questions=("How does onboarding work?",),
                )
            ]
        }
    )

    assert observations[0].granularity is DraftClaimGranularity.COMPOSITE
    assert observations[0].claim.value == "Onboarding includes several steps."


def test_parses_provenance_bearing_payload_without_changing_observation_content() -> (
    None
):
    observations = _parse(
        _provenance_payload(
            claims=(
                _claim_payload(
                    claim="Provenance payload still yields the same observation.",
                    possible_questions=("Does provenance affect parsing?",),
                ),
            ),
        ),
        artifact_ref=ArtifactRef("parsed-artifact-1"),
    )

    assert len(observations) == 1
    observation = observations[0]
    assert observation.observation_ref.value == "parsed-artifact-1:draft-claim:0"
    assert observation.source_unit_ref == SourceUnitRef("document-1.unit.0")
    assert (
        observation.claim.value
        == "Provenance payload still yields the same observation."
    )
    assert tuple(question.value for question in observation.possible_questions) == (
        "Does provenance affect parsing?",
    )


def test_provenance_bearing_payload_missing_mandatory_provenance_rejected() -> None:
    payload = _provenance_payload(claims=(_claim_payload(),))
    del payload["llm_attempt_id"]

    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse(payload)


def test_provenance_bearing_payload_wrong_provenance_type_rejected() -> None:
    payload = _provenance_payload(claims=(_claim_payload(),))
    payload["prompt_version"] = 2

    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse(payload)


def test_parses_multiple_claims_in_order() -> None:
    observations = _parse(
        {
            "claims": [
                _claim_payload(claim="First claim."),
                _claim_payload(claim="Second claim."),
                _claim_payload(claim="Third claim."),
            ]
        }
    )

    assert tuple(observation.claim.value for observation in observations) == (
        "First claim.",
        "Second claim.",
        "Third claim.",
    )


def test_empty_claims_returns_empty_tuple() -> None:
    assert _parse({"claims": []}) == ()


def test_wrong_artifact_kind_rejected() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse(
            {"claims": []},
            artifact_kind=ArtifactKind("knowledge_workbench.other.parsed"),
        )


def test_missing_claims_rejected() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({})


def test_extra_top_level_field_rejected() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [], "extra": True})


def test_missing_claim_field_rejected() -> None:
    claim_payload = _claim_payload()
    del claim_payload["evidence_block"]

    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [claim_payload]})


def test_extra_claim_field_rejected() -> None:
    claim_payload = _claim_payload()
    claim_payload["extra"] = "not allowed"

    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [claim_payload]})


def test_null_field_rejected() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [_claim_payload(claim=None)]})


def test_invalid_granularity_rejected() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [_claim_payload(granularity="surface")]})


def test_possible_questions_can_be_empty() -> None:
    observations = _parse({"claims": [_claim_payload(possible_questions=[])]})

    assert observations[0].possible_questions == ()


def test_possible_questions_must_be_array_of_strings() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [_claim_payload(possible_questions="What is it?")]})

    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [_claim_payload(possible_questions=("Valid?", 1))]})


def test_exclusion_scope_can_be_empty_string() -> None:
    observations = _parse({"claims": [_claim_payload(exclusion_scope="")]})

    assert observations[0].exclusion_scope.value == ""


def test_evidence_block_must_be_non_empty() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [_claim_payload(evidence_block=" ")]})


def test_refs_are_deterministic() -> None:
    observations = _parse(
        {
            "claims": [
                _claim_payload(claim="First claim."),
                _claim_payload(claim="Second claim."),
            ]
        },
        artifact_ref=ArtifactRef("parsed-artifact-9"),
    )

    assert tuple(observation.observation_ref.value for observation in observations) == (
        "parsed-artifact-9:draft-claim:0",
        "parsed-artifact-9:draft-claim:1",
    )


def test_source_unit_ref_assigned_to_every_observation() -> None:
    observations = _parse(
        {
            "claims": [
                _claim_payload(claim="First claim."),
                _claim_payload(claim="Second claim."),
            ]
        },
        source_unit_ref=SourceUnitRef("document-7.unit.3"),
    )

    assert tuple(observation.source_unit_ref.value for observation in observations) == (
        "document-7.unit.3",
        "document-7.unit.3",
    )


def test_no_ontology_fields_accepted() -> None:
    claim_payload = _claim_payload()
    claim_payload["confidence"] = 0.9

    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": [claim_payload]})


def test_claims_must_be_array() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": "not-array"})


def test_claim_item_must_be_object() -> None:
    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _parse({"claims": ["not-object"]})


def test_naive_created_at_rejected() -> None:
    with pytest.raises(ValueError):
        _parse(
            {"claims": []},
            created_at=datetime(2026, 6, 8, 12, 0),
        )


def test_parser_does_not_import_forbidden_runtimes_or_later_stages() -> None:
    text = PARSER_FILE.read_text(encoding="utf-8")

    forbidden_markers = (
        "llm_runtime",
        "execution_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "consolidation",
        "embedding",
        "publication",
        "registry",
        "surface",
        "Surface",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
