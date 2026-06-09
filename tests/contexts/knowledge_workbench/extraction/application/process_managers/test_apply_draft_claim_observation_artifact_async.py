from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import PipelineArtifact
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import ArtifactKind
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import ArtifactLineage
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import ArtifactPayload, JsonInputValue
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import ArtifactStatus
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import ArtifactVisibility
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import RetentionPolicy
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_artifact_parser import (
    EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    DraftClaimObservationArtifactParser,
    InvalidDraftClaimObservationArtifact,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import DraftClaimObservationProvenanceCandidate
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_application_unit_of_work_port import DraftClaimObservationApplicationEvent
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifactAsync,
    ApplyDraftClaimObservationArtifactCommand,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import DraftClaimObservation
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import SourceUnitRef


PROCESS_MANAGER_FILE = (
    Path(__file__).resolve().parents[6]
    / "src/contexts/knowledge_workbench/extraction/application/process_managers/apply_draft_claim_observation_artifact.py"
)


class FakeAsyncDraftClaimObservationApplicationUnitOfWork:
    def __init__(
        self,
        *,
        fail_on_provenance_save: bool = False,
        fail_on_commit: bool = False,
    ) -> None:
        self.saved_observations: tuple[DraftClaimObservation, ...] = ()
        self.saved_provenance_candidates: tuple[
            DraftClaimObservationProvenanceCandidate,
            ...,
        ] = ()
        self.events: tuple[DraftClaimObservationApplicationEvent, ...] = ()
        self.operations: list[str] = []
        self.committed = False
        self.rolled_back = False
        self.fail_on_provenance_save = fail_on_provenance_save
        self.fail_on_commit = fail_on_commit

    async def save_draft_claim_observations(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None:
        self.operations.append("save_observations")
        self.saved_observations = self.saved_observations + observations

    async def save_draft_claim_observation_provenance_candidates(
        self,
        candidates: tuple[DraftClaimObservationProvenanceCandidate, ...],
    ) -> None:
        self.operations.append("save_provenance_candidates")
        if self.fail_on_provenance_save:
            raise RuntimeError("provenance candidate save failed")
        self.saved_provenance_candidates = self.saved_provenance_candidates + candidates

    async def append_event(self, event: DraftClaimObservationApplicationEvent) -> None:
        self.operations.append("append_event")
        self.events = self.events + (event,)

    async def commit(self) -> None:
        self.operations.append("commit")
        if self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    async def rollback(self) -> None:
        self.operations.append("rollback")
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _claim_payload() -> dict[str, JsonInputValue]:
    return {
        "claim": "Product turns documents into knowledge.",
        "granularity": "atomic",
        "possible_questions": ("What does the product do?",),
        "exclusion_scope": "",
        "evidence_block": "turns documents into knowledge",
    }


def _provenance_payload(claims: JsonInputValue) -> dict[str, JsonInputValue]:
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
    artifact_kind: ArtifactKind = EXPECTED_DRAFT_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
) -> PipelineArtifact:
    return PipelineArtifact(
        artifact_ref=ArtifactRef("parsed-artifact-1"),
        artifact_kind=artifact_kind,
        payload=ArtifactPayload(payload),
        status=ArtifactStatus.VALIDATED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(parent_refs=(ArtifactRef("raw-artifact-1"),)),
        created_at=_now(),
        updated_at=_now(),
    )


def _command(artifact: PipelineArtifact) -> ApplyDraftClaimObservationArtifactCommand:
    return ApplyDraftClaimObservationArtifactCommand(
        parsed_artifact=artifact,
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        created_at=_now(),
        occurred_at=_now(),
    )


def _manager(
    unit_of_work: FakeAsyncDraftClaimObservationApplicationUnitOfWork,
) -> ApplyDraftClaimObservationArtifactAsync:
    return ApplyDraftClaimObservationArtifactAsync(
        parser=DraftClaimObservationArtifactParser(),
        unit_of_work=unit_of_work,
    )


@pytest.mark.asyncio
async def test_async_execute_saves_observations_provenance_event_and_commits_in_order() -> None:
    unit_of_work = FakeAsyncDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(_provenance_payload(claims=(_claim_payload(),)))

    result = await _manager(unit_of_work).execute(_command(artifact))

    assert unit_of_work.saved_observations == result.observations
    assert unit_of_work.saved_provenance_candidates == result.provenance_candidates
    assert unit_of_work.events == (result.event,)
    assert unit_of_work.committed is True
    assert unit_of_work.rolled_back is False
    assert unit_of_work.operations == [
        "save_observations",
        "save_provenance_candidates",
        "append_event",
        "commit",
    ]


@pytest.mark.asyncio
async def test_async_execute_rolls_back_when_provenance_save_fails() -> None:
    unit_of_work = FakeAsyncDraftClaimObservationApplicationUnitOfWork(
        fail_on_provenance_save=True,
    )
    artifact = _artifact(_provenance_payload(claims=(_claim_payload(),)))

    with pytest.raises(RuntimeError, match="provenance candidate save failed"):
        await _manager(unit_of_work).execute(_command(artifact))

    assert len(unit_of_work.saved_observations) == 1
    assert unit_of_work.saved_provenance_candidates == ()
    assert unit_of_work.events == ()
    assert unit_of_work.committed is False
    assert unit_of_work.rolled_back is True
    assert unit_of_work.operations == [
        "save_observations",
        "save_provenance_candidates",
        "rollback",
    ]


@pytest.mark.asyncio
async def test_async_execute_rolls_back_on_parser_failure() -> None:
    unit_of_work = FakeAsyncDraftClaimObservationApplicationUnitOfWork()
    artifact = _artifact(
        _provenance_payload(claims=()),
        artifact_kind=ArtifactKind("knowledge_workbench.other.parsed"),
    )

    with pytest.raises(InvalidDraftClaimObservationArtifact):
        await _manager(unit_of_work).execute(_command(artifact))

    assert unit_of_work.saved_observations == ()
    assert unit_of_work.saved_provenance_candidates == ()
    assert unit_of_work.events == ()
    assert unit_of_work.committed is False
    assert unit_of_work.rolled_back is True
    assert unit_of_work.operations == ["rollback"]


def test_async_apply_uses_async_uow_and_does_not_import_db_or_later_stage_concepts() -> None:
    text = PROCESS_MANAGER_FILE.read_text(encoding="utf-8")

    required_markers = (
        "class ApplyDraftClaimObservationArtifactAsync",
        "AsyncDraftClaimObservationApplicationUnitOfWorkPort",
        "await self._unit_of_work.save_draft_claim_observations",
        "await self._unit_of_work.save_draft_claim_observation_provenance_candidates",
        "await self._unit_of_work.append_event",
        "await self._unit_of_work.commit",
        "await self._unit_of_work.rollback",
    )
    forbidden_markers = (
        "Postgres",
        "postgres",
        "asyncpg",
        "provider",
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

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
