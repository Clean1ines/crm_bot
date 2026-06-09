from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

import pytest

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
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
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import (
    DraftClaimObservationProvenanceCandidateBuilder,
    InvalidDraftClaimObservationProvenanceCandidate,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _claim_payload(*, claim: str) -> Mapping[str, JsonInputValue]:
    return {
        "claim": claim,
        "granularity": "atomic",
        "possible_questions": ("What does it do?",),
        "exclusion_scope": "",
        "evidence_block": claim,
    }


def _payload(
    *, claims: tuple[Mapping[str, JsonInputValue], ...]
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
        "raw_artifact_ref": "raw-artifact-1",
        "claims": claims,
    }


def _artifact(
    payload: dict[str, JsonInputValue],
    *,
    lineage: ArtifactLineage = ArtifactLineage(
        parent_refs=(ArtifactRef("raw-artifact-1"),)
    ),
    artifact_ref: ArtifactRef = ArtifactRef("parsed-artifact-1"),
) -> PipelineArtifact:
    return PipelineArtifact(
        artifact_ref=artifact_ref,
        artifact_kind=EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
        payload=ArtifactPayload(payload),
        status=ArtifactStatus.VALIDATED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=lineage,
        created_at=_now(),
        updated_at=_now(),
    )


def _observations(artifact: PipelineArtifact):
    return DraftClaimObservationArtifactParser().parse(
        DraftClaimObservationArtifactParserInput(
            artifact=artifact,
            source_unit_ref=SourceUnitRef("document-1.unit.0"),
            created_at=_now(),
        )
    )


def test_one_claim_produces_one_provenance_candidate() -> None:
    artifact = _artifact(_payload(claims=(_claim_payload(claim="First claim."),)))
    observations = _observations(artifact)

    candidates = DraftClaimObservationProvenanceCandidateBuilder().build(
        parsed_artifact=artifact,
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        observations=observations,
        created_at=_now(),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.observation_ref == observations[0].observation_ref
    assert candidate.source_unit_ref == SourceUnitRef("document-1.unit.0")
    assert candidate.workflow_run_id == "workflow-1"
    assert candidate.stage_run_id == "stage-1"
    assert candidate.work_item_id == "work-item-1"
    assert candidate.work_item_attempt_id == "work-attempt-1"
    assert candidate.llm_task_id == "llm-task-1"
    assert candidate.llm_attempt_id == "llm-attempt-1"
    assert candidate.prompt_id == "prompt-a"
    assert candidate.prompt_version == "v1"
    assert candidate.raw_artifact_ref == ArtifactRef("raw-artifact-1")
    assert candidate.parsed_artifact_ref == ArtifactRef("parsed-artifact-1")
    assert candidate.claim_index == 0
    assert candidate.created_at == _now()


def test_two_claims_produce_claim_indexes_zero_and_one() -> None:
    artifact = _artifact(
        _payload(
            claims=(
                _claim_payload(claim="First claim."),
                _claim_payload(claim="Second claim."),
            )
        )
    )
    observations = _observations(artifact)

    candidates = DraftClaimObservationProvenanceCandidateBuilder().build(
        parsed_artifact=artifact,
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        observations=observations,
        created_at=_now(),
    )

    assert tuple(candidate.claim_index for candidate in candidates) == (0, 1)
    assert tuple(candidate.observation_ref for candidate in candidates) == tuple(
        observation.observation_ref for observation in observations
    )


def test_candidate_parsed_artifact_ref_matches_input_artifact() -> None:
    artifact = _artifact(
        _payload(claims=(_claim_payload(claim="First claim."),)),
        artifact_ref=ArtifactRef("parsed-artifact-9"),
    )

    candidates = DraftClaimObservationProvenanceCandidateBuilder().build(
        parsed_artifact=artifact,
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        observations=_observations(artifact),
        created_at=_now(),
    )

    assert candidates[0].parsed_artifact_ref == ArtifactRef("parsed-artifact-9")


def test_raw_artifact_ref_comes_from_explicit_payload_and_lineage() -> None:
    artifact = _artifact(
        _payload(claims=(_claim_payload(claim="First claim."),)),
        lineage=ArtifactLineage(parent_refs=(ArtifactRef("raw-artifact-1"),)),
    )

    candidates = DraftClaimObservationProvenanceCandidateBuilder().build(
        parsed_artifact=artifact,
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        observations=_observations(artifact),
        created_at=_now(),
    )

    assert candidates[0].raw_artifact_ref == ArtifactRef("raw-artifact-1")


def test_missing_raw_artifact_ref_rejected() -> None:
    payload = _payload(claims=(_claim_payload(claim="First claim."),))
    del payload["raw_artifact_ref"]
    artifact = _artifact(payload)

    with pytest.raises(InvalidDraftClaimObservationProvenanceCandidate):
        DraftClaimObservationProvenanceCandidateBuilder().build(
            parsed_artifact=artifact,
            source_unit_ref=SourceUnitRef("document-1.unit.0"),
            observations=(),
            created_at=_now(),
        )


def test_missing_workflow_run_id_rejected() -> None:
    payload = _payload(claims=(_claim_payload(claim="First claim."),))
    del payload["workflow_run_id"]
    artifact = _artifact(payload)

    with pytest.raises(InvalidDraftClaimObservationProvenanceCandidate):
        DraftClaimObservationProvenanceCandidateBuilder().build(
            parsed_artifact=artifact,
            source_unit_ref=SourceUnitRef("document-1.unit.0"),
            observations=(),
            created_at=_now(),
        )


def test_lineage_mismatch_rejected() -> None:
    artifact = _artifact(
        _payload(claims=(_claim_payload(claim="First claim."),)),
        lineage=ArtifactLineage(parent_refs=(ArtifactRef("different-raw-artifact"),)),
    )

    with pytest.raises(
        InvalidDraftClaimObservationProvenanceCandidate,
        match="raw_artifact_ref must match parsed artifact lineage",
    ):
        DraftClaimObservationProvenanceCandidateBuilder().build(
            parsed_artifact=artifact,
            source_unit_ref=SourceUnitRef("document-1.unit.0"),
            observations=_observations(artifact),
            created_at=_now(),
        )


def test_legacy_claims_only_payload_rejected_for_provenance_candidates() -> None:
    artifact = _artifact({"claims": (_claim_payload(claim="First claim."),)})

    with pytest.raises(InvalidDraftClaimObservationProvenanceCandidate):
        DraftClaimObservationProvenanceCandidateBuilder().build(
            parsed_artifact=artifact,
            source_unit_ref=SourceUnitRef("document-1.unit.0"),
            observations=_observations(artifact),
            created_at=_now(),
        )


def test_naive_created_at_rejected() -> None:
    artifact = _artifact(_payload(claims=()))

    with pytest.raises(
        InvalidDraftClaimObservationProvenanceCandidate,
        match="created_at must be timezone-aware",
    ):
        DraftClaimObservationProvenanceCandidateBuilder().build(
            parsed_artifact=artifact,
            source_unit_ref=SourceUnitRef("document-1.unit.0"),
            observations=(),
            created_at=datetime(2026, 6, 8, 12, 0),
        )


def test_source_unit_ref_mismatch_rejected() -> None:
    artifact = _artifact(_payload(claims=()))

    with pytest.raises(
        InvalidDraftClaimObservationProvenanceCandidate,
        match="source_unit_ref must match parsed artifact provenance",
    ):
        DraftClaimObservationProvenanceCandidateBuilder().build(
            parsed_artifact=artifact,
            source_unit_ref=SourceUnitRef("document-2.unit.0"),
            observations=(),
            created_at=_now(),
        )


def test_candidate_contract_rejects_negative_claim_index() -> None:
    artifact = _artifact(_payload(claims=(_claim_payload(claim="First claim."),)))
    candidate = DraftClaimObservationProvenanceCandidateBuilder().build(
        parsed_artifact=artifact,
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        observations=_observations(artifact),
        created_at=_now(),
    )[0]

    with pytest.raises(
        InvalidDraftClaimObservationProvenanceCandidate,
        match="claim_index must be >= 0",
    ):
        type(candidate)(
            observation_ref=candidate.observation_ref,
            source_unit_ref=candidate.source_unit_ref,
            workflow_run_id=candidate.workflow_run_id,
            stage_run_id=candidate.stage_run_id,
            work_item_id=candidate.work_item_id,
            work_item_attempt_id=candidate.work_item_attempt_id,
            llm_task_id=candidate.llm_task_id,
            llm_attempt_id=candidate.llm_attempt_id,
            prompt_id=candidate.prompt_id,
            prompt_version=candidate.prompt_version,
            raw_artifact_ref=candidate.raw_artifact_ref,
            parsed_artifact_ref=candidate.parsed_artifact_ref,
            claim_index=-1,
            created_at=candidate.created_at,
        )


def test_builder_does_not_import_db_runtime_provider_or_later_stage_concepts() -> None:
    import pathlib

    path = pathlib.Path(
        "src/contexts/knowledge_workbench/extraction/application/policies/"
        "draft_claim_observation_provenance_candidate_builder.py"
    )
    text = path.read_text(encoding="utf-8")

    forbidden_markers = (
        "Postgres",
        "postgres",
        "llm_runtime",
        "execution_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "consolidation",
        "publication",
        "surface",
        "Surface",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
