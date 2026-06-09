from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import (
    DraftClaimObservationProvenanceCandidate,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_application_unit_of_work_port import (
    AsyncDraftClaimObservationApplicationUnitOfWorkPort,
    DraftClaimObservationApplicationEvent,
    DraftClaimObservationApplicationUnitOfWorkPort,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.events.draft_claim_observation_events import (
    DraftClaimObservationsApplied,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_text import (
    DraftClaimText,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.evidence_block import (
    EvidenceBlock,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.exclusion_scope import (
    ExclusionScope,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.possible_question import (
    PossibleQuestion,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


ROOT = Path(__file__).resolve().parents[6]
PORT_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "ports"
    / "draft_claim_observation_application_unit_of_work_port.py"
)
EVENT_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "domain"
    / "events"
    / "draft_claim_observation_events.py"
)


class FakeDraftClaimObservationApplicationUnitOfWork:
    def __init__(self) -> None:
        self.saved_observations: tuple[DraftClaimObservation, ...] = ()
        self.saved_provenance_candidates: tuple[
            DraftClaimObservationProvenanceCandidate,
            ...,
        ] = ()
        self.events: tuple[DraftClaimObservationApplicationEvent, ...] = ()
        self.committed = False
        self.rolled_back = False

    def save_draft_claim_observations(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None:
        self.saved_observations = self.saved_observations + observations

    def save_draft_claim_observation_provenance_candidates(
        self,
        candidates: tuple[DraftClaimObservationProvenanceCandidate, ...],
    ) -> None:
        self.saved_provenance_candidates = self.saved_provenance_candidates + candidates

    def append_event(self, event: DraftClaimObservationApplicationEvent) -> None:
        self.events = self.events + (event,)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeAsyncDraftClaimObservationApplicationUnitOfWork:
    def __init__(self) -> None:
        self.saved_observations: tuple[DraftClaimObservation, ...] = ()
        self.saved_provenance_candidates: tuple[
            DraftClaimObservationProvenanceCandidate,
            ...,
        ] = ()
        self.events: tuple[DraftClaimObservationApplicationEvent, ...] = ()
        self.committed = False
        self.rolled_back = False

    async def save_draft_claim_observations(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None:
        self.saved_observations = self.saved_observations + observations

    async def save_draft_claim_observation_provenance_candidates(
        self,
        candidates: tuple[DraftClaimObservationProvenanceCandidate, ...],
    ) -> None:
        self.saved_provenance_candidates = self.saved_provenance_candidates + candidates

    async def append_event(self, event: DraftClaimObservationApplicationEvent) -> None:
        self.events = self.events + (event,)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _accept_unit_of_work(
    unit_of_work: DraftClaimObservationApplicationUnitOfWorkPort,
) -> DraftClaimObservationApplicationUnitOfWorkPort:
    return unit_of_work


def _accept_async_unit_of_work(
    unit_of_work: AsyncDraftClaimObservationApplicationUnitOfWorkPort,
) -> AsyncDraftClaimObservationApplicationUnitOfWorkPort:
    return unit_of_work


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _observation(
    observation_ref: str = "artifact-1:draft-claim:0",
    source_unit_ref: str = "document-1.unit.0",
) -> DraftClaimObservation:
    return DraftClaimObservation(
        observation_ref=DraftClaimObservationRef(observation_ref),
        source_unit_ref=SourceUnitRef(source_unit_ref),
        claim=DraftClaimText("Product turns documents into knowledge."),
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=(PossibleQuestion("What does the product do?"),),
        exclusion_scope=ExclusionScope(""),
        evidence_block=EvidenceBlock("turns documents into knowledge"),
        created_at=_now(),
    )


def _provenance_candidate(
    observation_ref: str = "artifact-1:draft-claim:0",
) -> DraftClaimObservationProvenanceCandidate:
    return DraftClaimObservationProvenanceCandidate(
        observation_ref=DraftClaimObservationRef(observation_ref),
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        work_item_id="work-item-1",
        work_item_attempt_id="work-attempt-1",
        llm_task_id="llm-task-1",
        llm_attempt_id="llm-attempt-1",
        prompt_id="prompt-a",
        prompt_version="v1",
        raw_artifact_ref=ArtifactRef("raw-artifact-1"),
        parsed_artifact_ref=ArtifactRef("parsed-artifact-1"),
        claim_index=0,
        created_at=_now(),
    )


def _event(
    *,
    observation_count: int = 1,
    occurred_at: datetime | None = None,
) -> DraftClaimObservationsApplied:
    return DraftClaimObservationsApplied(
        artifact_ref=ArtifactRef("artifact-1"),
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        observation_count=observation_count,
        occurred_at=occurred_at or _now(),
    )


def test_fake_unit_of_work_implements_port_contract() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()

    accepted = _accept_unit_of_work(unit_of_work)

    accepted.save_draft_claim_observations((_observation(),))
    accepted.save_draft_claim_observation_provenance_candidates(
        (_provenance_candidate(),),
    )
    accepted.append_event(_event())
    accepted.commit()
    accepted.rollback()

    assert unit_of_work.saved_observations == (_observation(),)
    assert unit_of_work.saved_provenance_candidates == (_provenance_candidate(),)
    assert unit_of_work.events == (_event(),)
    assert unit_of_work.committed is True
    assert unit_of_work.rolled_back is True


@pytest.mark.asyncio
async def test_fake_async_unit_of_work_implements_async_port_contract() -> None:
    unit_of_work = FakeAsyncDraftClaimObservationApplicationUnitOfWork()

    accepted = _accept_async_unit_of_work(unit_of_work)

    await accepted.save_draft_claim_observations((_observation(),))
    await accepted.save_draft_claim_observation_provenance_candidates(
        (_provenance_candidate(),),
    )
    await accepted.append_event(_event())
    await accepted.commit()
    await accepted.rollback()

    assert unit_of_work.saved_observations == (_observation(),)
    assert unit_of_work.saved_provenance_candidates == (_provenance_candidate(),)
    assert unit_of_work.events == (_event(),)
    assert unit_of_work.committed is True
    assert unit_of_work.rolled_back is True


def test_can_save_observations_provenance_candidates_event_and_commit() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    observation = _observation()
    provenance_candidate = _provenance_candidate()
    event = _event(observation_count=1)

    unit_of_work.save_draft_claim_observations((observation,))
    unit_of_work.save_draft_claim_observation_provenance_candidates(
        (provenance_candidate,),
    )
    unit_of_work.append_event(event)
    unit_of_work.commit()

    assert unit_of_work.saved_observations == (observation,)
    assert unit_of_work.saved_provenance_candidates == (provenance_candidate,)
    assert unit_of_work.events == (event,)
    assert unit_of_work.committed is True
    assert unit_of_work.rolled_back is False


def test_rollback_can_be_called() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()

    unit_of_work.rollback()

    assert unit_of_work.rolled_back is True
    assert unit_of_work.committed is False


def test_event_validates_timezone() -> None:
    with pytest.raises(ValueError):
        _event(occurred_at=datetime(2026, 6, 8, 12, 0))


def test_event_accepts_zero_observations() -> None:
    event = _event(observation_count=0)

    assert event.observation_count == 0


def test_event_rejects_negative_observation_count() -> None:
    with pytest.raises(ValueError):
        _event(observation_count=-1)


def test_unit_of_work_accepts_empty_observation_and_provenance_tuples() -> None:
    unit_of_work = FakeDraftClaimObservationApplicationUnitOfWork()
    event = _event(observation_count=0)

    unit_of_work.save_draft_claim_observations(())
    unit_of_work.save_draft_claim_observation_provenance_candidates(())
    unit_of_work.append_event(event)
    unit_of_work.commit()

    assert unit_of_work.saved_observations == ()
    assert unit_of_work.saved_provenance_candidates == ()
    assert unit_of_work.events == (event,)
    assert unit_of_work.committed is True


def test_port_contract_names_required_persistence_methods() -> None:
    text = PORT_FILE.read_text(encoding="utf-8")

    required_methods = (
        "class DraftClaimObservationApplicationUnitOfWorkPort",
        "class AsyncDraftClaimObservationApplicationUnitOfWorkPort",
        "def save_draft_claim_observations(",
        "def save_draft_claim_observation_provenance_candidates(",
        "def append_event(",
        "def commit(",
        "def rollback(",
    )

    missing = [method for method in required_methods if method not in text]

    assert not missing, "\n".join(missing)


def test_port_and_event_files_do_not_import_or_name_later_stage_concepts() -> None:
    forbidden_markers = (
        "PipelineArtifact",
        "ArtifactPayload",
        "llm_runtime",
        "execution_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "Ontology",
        "ClaimType",
        "ClaimTriple",
        "ClaimRelation",
        "CanonicalIntent",
        "registry",
        "surface",
        "Surface",
    )

    offenders: list[str] = []
    for path in (PORT_FILE, EVENT_FILE):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker!r}")

    assert not offenders
