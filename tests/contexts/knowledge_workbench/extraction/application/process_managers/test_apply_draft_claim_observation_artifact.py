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
    InvalidDraftClaimObservationArtifact,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import (
    InvalidDraftClaimObservationProvenanceCandidate,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifact,
    ApplyDraftClaimObservationArtifactCommand,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_application_unit_of_work_port import (
    DraftClaimObservationApplicationEvent,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


ROOT = Path(__file__).resolve().parents[6]
PROCESS_MANAGER_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "process_managers"
    / "apply_draft_claim_observation_artifact.py"
)


class FakeDraftClaimObservationApplicationUnitOfWork:
    def __init__(self, *, fail_on_commit: bool = False) -> None:
        self.saved_observations: tuple[DraftClaimObservation, ...] = ()
        self.events: tuple[DraftClaimObservationApplicationEvent, ...] = ()
        self.actions: tuple[str, ...] = ()
        self.fail_on_commit = fail_on_commit

    def save_draft_claim_observations(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None:
        self.actions = self.actions + ("save_draft_claim_observations",)
        self.saved_observations = self.saved_observations + observations

    def append_event(
        self,
        event: DraftClaimObservationApplicationEvent,
    ) -> None:
        self.actions = self.actions + ("append_event",)
        self.events = self.events + (event,)

    def commit(self) -> None:
        self.actions = self.actions + ("commit",)
        if self.fail_on_commit:
            raise RuntimeError("commit failed")

    def rollback(self) -> None:
        self.actions = self.actions + ("rollback",)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _claim_payload(
    *,
    claim: JsonInputValue = "Product turns documents into knowledge.",
    granularity: JsonInputValue = "atomic",
    possible_questions: JsonInputValue = ("What does the product do?",),
    exclusion_scope: JsonInputValue = "",
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
    source_unit_ref: JsonInputValue = "document-1.unit.0",
) -> dict[str, JsonInputValue]:
    return {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "stage-1",
        "source_unit_ref": source_unit_ref,
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
    artifact_ref: ArtifactRef = ArtifactRef("parsed-artifact-1"),
    lineage: ArtifactLineage = ArtifactLineage(parent_refs=(ArtifactRef("raw-artifact-1"),)),
) -> PipelineArtifact:
    return PipelineArtifact(
        artifact_ref=artifact_ref,
        artifact_kind=artifact_kind,
        payload=ArtifactPayload(payload),
        status=ArtifactStatus.VALIDATED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=lineage,
        created_at=_now(),
        updated_at=_now(),
    )


def _command(
    artifact: PipelineArtifact,
    *,
    source_unit_ref: SourceUnitRef = SourceUnitRef("document-1.unit.0"),
    created_at: datetime | None = None,
    occurred_at: datetime | None = None,
) -> ApplyDraftClaimObservationArtifactCommand:
    return ApplyDraftClaimObservationArtifactCommand(
        parsed_artifact=artifact,
        source_unit_ref=source_unit_ref,
        created_at=created_at or _now(),
        occurred_at=occurred_at or _now(),
    )


def _manager(
    unit_of_work: FakeDraftClaimObservationApplicationUnitOfWork,
) -> ApplyDraftClaimObservationArtifact:
    return ApplyDraftClaimObservationArtifact(
        parser=DraftClaimObservationArtifactParser(),
        unit_of_work=unit_of_work,
    )


def test_applies_one_observation_and_commits() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(_provenance_payload(claims=(_claim_payload(),)))

    result = _manager(unit_of_work).execute(_command(artifact))

    assert len(result.observations) == 1
    assert result.observations[0].claim.value == (
        "Product turns documents into knowledge."
    )
    assert len(result.provenance_candidates) == 1
    assert result.provenance_candidates[0].observation_ref == (
        result.observations[0].observation_ref
    )
    assert result.provenance_candidates[0].parsed_artifact_ref == artifact.artifact_ref
    assert result.provenance_candidates[0].raw_artifact_ref == ArtifactRef("raw-artifact-1")
    assert unit_of_work.saved_observations == result.observations
    assert unit_of_work.events == (result.event,)
    assert unit_of_work.actions == (
        "save_draft_claim_observations",
        "append_event",
        "commit",
    )


def test_applies_empty_observations_and_commits_count_zero() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(_provenance_payload(claims=()))

    result = _manager(unit_of_work).execute(_command(artifact))

    assert result.observations == ()
    assert result.provenance_candidates == ()
    assert result.event.observation_count == 0
    assert unit_of_work.saved_observations == ()
    assert unit_of_work.events == (result.event,)
    assert unit_of_work.actions == (
        "save_draft_claim_observations",
        "append_event",
        "commit",
    )


def test_provenance_candidates_are_not_persisted_yet() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(_provenance_payload(claims=(_claim_payload(),)))

    result = _manager(unit_of_work).execute(_command(artifact))

    assert len(result.provenance_candidates) == 1
    assert not hasattr(unit_of_work, "saved_provenance_candidates")
    assert unit_of_work.actions == (
        "save_draft_claim_observations",
        "append_event",
        "commit",
    )


def test_parser_failure_rolls_back() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(
        _provenance_payload(claims=()),
        artifact_kind=ArtifactKind("knowledge_workbench.other.parsed"),
    )

    with pytest.raises(InvalidDraftClaimObservationArtifact):
        _manager(unit_of_work).execute(_command(artifact))

    assert unit_of_work.saved_observations == ()
    assert unit_of_work.events == ()
    assert unit_of_work.actions == ("rollback",)


def test_provenance_failure_rolls_back_without_persisting_observations() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(
        _provenance_payload(claims=(_claim_payload(),), source_unit_ref="document-2.unit.0"),
    )

    with pytest.raises(InvalidDraftClaimObservationProvenanceCandidate):
        _manager(unit_of_work).execute(_command(artifact))

    assert unit_of_work.saved_observations == ()
    assert unit_of_work.events == ()
    assert unit_of_work.actions == ("rollback",)


def test_commit_failure_rolls_back() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork(fail_on_commit=True)
    artifact = _artifact(_provenance_payload(claims=(_claim_payload(),)))

    with pytest.raises(RuntimeError):
        _manager(unit_of_work).execute(_command(artifact))

    assert len(unit_of_work.saved_observations) == 1
    assert len(unit_of_work.events) == 1
    assert unit_of_work.actions == (
        "save_draft_claim_observations",
        "append_event",
        "commit",
        "rollback",
    )


def test_event_has_artifact_ref_source_unit_ref_and_count() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(
        _provenance_payload(
            claims=(
                _claim_payload(claim="First claim."),
                _claim_payload(claim="Second claim."),
            )
        ),
        artifact_ref=ArtifactRef("parsed-artifact-9"),
    )
    source_unit_ref = SourceUnitRef("document-1.unit.0")

    result = _manager(unit_of_work).execute(
        _command(artifact, source_unit_ref=source_unit_ref)
    )

    assert result.event.artifact_ref.value == "parsed-artifact-9"
    assert result.event.source_unit_ref == source_unit_ref
    assert result.event.observation_count == 2
    assert result.event.occurred_at == _now()
    assert tuple(candidate.claim_index for candidate in result.provenance_candidates) == (0, 1)


def test_actions_order_is_save_event_commit() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(_provenance_payload(claims=(_claim_payload(),)))

    _manager(unit_of_work).execute(_command(artifact))

    assert unit_of_work.actions == (
        "save_draft_claim_observations",
        "append_event",
        "commit",
    )


def test_command_requires_timezone_aware_timestamps() -> None:
    artifact = _artifact(_provenance_payload(claims=()))
    naive = datetime(2026, 6, 8, 12, 0)

    with pytest.raises(ValueError):
        _command(artifact, created_at=naive)

    with pytest.raises(ValueError):
        _command(artifact, occurred_at=naive)


def test_process_manager_does_not_import_db_provider_or_later_stage_concepts() -> None:
    text = PROCESS_MANAGER_FILE.read_text(encoding="utf-8")

    forbidden_markers = (
        "Postgres",
        "postgres",
        "provider",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "WorkItem",
        "LlmTask",
        "final",
        "surface",
        "Surface",
        "Ontology",
        "ClaimType",
        "ClaimTriple",
        "ClaimRelation",
        "CanonicalIntent",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
