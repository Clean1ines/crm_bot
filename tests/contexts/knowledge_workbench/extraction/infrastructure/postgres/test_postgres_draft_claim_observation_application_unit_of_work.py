from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import DraftClaimObservationProvenanceCandidate
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import DraftClaimObservation
from src.contexts.knowledge_workbench.extraction.domain.events.draft_claim_observation_events import DraftClaimObservationsApplied
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import DraftClaimGranularity
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import DraftClaimObservationRef
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_text import DraftClaimText
from src.contexts.knowledge_workbench.extraction.domain.value_objects.evidence_block import EvidenceBlock
from src.contexts.knowledge_workbench.extraction.domain.value_objects.exclusion_scope import ExclusionScope
from src.contexts.knowledge_workbench.extraction.domain.value_objects.possible_question import PossibleQuestion
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_application_unit_of_work import (
    DraftClaimObservationUnitOfWorkClosedError,
    PostgresDraftClaimObservationApplicationUnitOfWork,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import SourceUnitRef


ROOT = Path(__file__).resolve().parents[6]
ADAPTER_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "infrastructure"
    / "postgres"
    / "postgres_draft_claim_observation_application_unit_of_work.py"
)


@dataclass(slots=True)
class FakeDatabaseState:
    observations: dict[str, tuple[object, ...]] = field(default_factory=dict)
    possible_questions: list[tuple[object, ...]] = field(default_factory=list)
    provenance: dict[str, tuple[object, ...]] = field(default_factory=dict)
    outbox_events: list[tuple[object, ...]] = field(default_factory=list)

    def clone(self) -> FakeDatabaseState:
        return FakeDatabaseState(
            observations=dict(self.observations),
            possible_questions=list(self.possible_questions),
            provenance=dict(self.provenance),
            outbox_events=list(self.outbox_events),
        )


@dataclass(slots=True)
class FakeTransaction:
    connection: FakeConnection
    started: int = 0
    committed: int = 0
    rolled_back: int = 0

    async def start(self) -> None:
        self.started += 1
        self.connection.pending_state = self.connection.committed_state.clone()

    async def commit(self) -> None:
        self.committed += 1
        if self.connection.pending_state is None:
            raise RuntimeError("transaction not started")
        self.connection.committed_state = self.connection.pending_state
        self.connection.pending_state = None

    async def rollback(self) -> None:
        self.rolled_back += 1
        self.connection.pending_state = None


@dataclass(slots=True)
class FakeConnection:
    committed_state: FakeDatabaseState = field(default_factory=FakeDatabaseState)
    pending_state: FakeDatabaseState | None = None
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    transaction_obj: FakeTransaction | None = None

    def transaction(self) -> FakeTransaction:
        if self.transaction_obj is None:
            self.transaction_obj = FakeTransaction(connection=self)
        return self.transaction_obj

    async def execute(self, query: str, *args: object) -> object:
        self.calls.append((query, args))
        state = self._state()
        normalized = " ".join(query.split())
        if "INSERT INTO draft_claim_observations" in normalized:
            state.observations[str(args[0])] = args
            return "OK"
        if "DELETE FROM draft_claim_observation_possible_questions" in normalized:
            state.possible_questions = [
                row for row in state.possible_questions if row[0] != args[0]
            ]
            return "OK"
        if "INSERT INTO draft_claim_observation_possible_questions" in normalized:
            state.possible_questions.append(args)
            return "OK"
        if "INSERT INTO draft_claim_observation_provenance" in normalized:
            observation_ref = str(args[0])
            if observation_ref not in state.observations:
                raise RuntimeError("draft_claim_observation_provenance observation FK failed")
            state.provenance[observation_ref] = args
            return "OK"
        if "INSERT INTO outbox_events" in normalized:
            state.outbox_events.append(args)
            return "OK"
        raise AssertionError(f"Unhandled SQL: {normalized}")

    def _state(self) -> FakeDatabaseState:
        if self.pending_state is None:
            raise RuntimeError("transaction not started")
        return self.pending_state


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _observation(
    *,
    observation_ref: str = "parsed-artifact-1:draft-claim:0",
    possible_questions: tuple[PossibleQuestion, ...] = (
        PossibleQuestion("What does the product do?"),
        PossibleQuestion("What does it turn documents into?"),
    ),
) -> DraftClaimObservation:
    return DraftClaimObservation(
        observation_ref=DraftClaimObservationRef(observation_ref),
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        claim=DraftClaimText("Product turns documents into knowledge."),
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=possible_questions,
        exclusion_scope=ExclusionScope(""),
        evidence_block=EvidenceBlock("turns documents into knowledge"),
        created_at=_now(),
    )


def _provenance_candidate(
    observation_ref: str = "parsed-artifact-1:draft-claim:0",
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


def _event(observation_count: int = 1) -> DraftClaimObservationsApplied:
    return DraftClaimObservationsApplied(
        artifact_ref=ArtifactRef("parsed-artifact-1"),
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        observation_count=observation_count,
        occurred_at=_now(),
    )


@pytest.mark.asyncio
async def test_saves_observations_possible_questions_provenance_and_outbox_in_one_commit() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresDraftClaimObservationApplicationUnitOfWork(connection)
    observation = _observation()
    provenance_candidate = _provenance_candidate()
    event = _event(observation_count=1)

    await unit_of_work.save_draft_claim_observations((observation,))
    await unit_of_work.save_draft_claim_observation_provenance_candidates(
        (provenance_candidate,),
    )
    await unit_of_work.append_event(event)
    await unit_of_work.commit()

    state = connection.committed_state
    assert len(state.observations) == 1
    observation_row = state.observations["parsed-artifact-1:draft-claim:0"]
    assert observation_row[0] == "parsed-artifact-1:draft-claim:0"
    assert observation_row[1] == "document-1.unit.0"
    assert observation_row[2] == "Product turns documents into knowledge."
    assert observation_row[3] == "atomic"
    assert observation_row[4] == ""
    assert observation_row[5] == "turns documents into knowledge"

    assert state.possible_questions == [
        ("parsed-artifact-1:draft-claim:0", 0, "What does the product do?"),
        (
            "parsed-artifact-1:draft-claim:0",
            1,
            "What does it turn documents into?",
        ),
    ]

    assert len(state.provenance) == 1
    provenance_row = state.provenance["parsed-artifact-1:draft-claim:0"]
    assert provenance_row[0] == "parsed-artifact-1:draft-claim:0"
    assert provenance_row[1] == "document-1.unit.0"
    assert provenance_row[2] == "workflow-1"
    assert provenance_row[3] == "stage-1"
    assert provenance_row[4] == "work-item-1"
    assert provenance_row[5] == "work-attempt-1"
    assert provenance_row[6] == "llm-task-1"
    assert provenance_row[7] == "llm-attempt-1"
    assert provenance_row[8] == "prompt-a"
    assert provenance_row[9] == "v1"
    assert provenance_row[10] == "raw-artifact-1"
    assert provenance_row[11] == "parsed-artifact-1"
    assert provenance_row[12] == 0

    assert len(state.outbox_events) == 1
    outbox_row = state.outbox_events[0]
    assert isinstance(outbox_row[0], str)
    assert outbox_row[1] == (
        "knowledge_workbench.extraction.draft_claim_observations_applied"
    )
    assert outbox_row[2] == "parsed-artifact-1"
    assert outbox_row[3]["artifact_ref"] == "parsed-artifact-1"
    assert outbox_row[3]["source_unit_ref"] == "document-1.unit.0"
    assert outbox_row[3]["observation_count"] == 1
    assert outbox_row[3]["occurred_at"] == _now().isoformat()
    assert connection.transaction_obj is not None
    assert connection.transaction_obj.started == 1
    assert connection.transaction_obj.committed == 1


@pytest.mark.asyncio
async def test_rollback_prevents_all_rows() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresDraftClaimObservationApplicationUnitOfWork(connection)

    await unit_of_work.save_draft_claim_observations((_observation(),))
    await unit_of_work.save_draft_claim_observation_provenance_candidates(
        (_provenance_candidate(),),
    )
    await unit_of_work.append_event(_event())
    await unit_of_work.rollback()

    state = connection.committed_state
    assert state.observations == {}
    assert state.possible_questions == []
    assert state.provenance == {}
    assert state.outbox_events == []
    assert connection.transaction_obj is not None
    assert connection.transaction_obj.rolled_back == 1


@pytest.mark.asyncio
async def test_provenance_cannot_be_saved_before_observation() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresDraftClaimObservationApplicationUnitOfWork(connection)

    with pytest.raises(RuntimeError, match="observation FK failed"):
        await unit_of_work.save_draft_claim_observation_provenance_candidates(
            (_provenance_candidate(),),
        )

    await unit_of_work.rollback()
    assert connection.committed_state.provenance == {}


@pytest.mark.asyncio
async def test_empty_observations_and_provenance_are_noop_but_event_can_be_saved() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresDraftClaimObservationApplicationUnitOfWork(connection)

    await unit_of_work.save_draft_claim_observations(())
    await unit_of_work.save_draft_claim_observation_provenance_candidates(())
    await unit_of_work.append_event(_event(observation_count=0))
    await unit_of_work.commit()

    state = connection.committed_state
    assert state.observations == {}
    assert state.possible_questions == []
    assert state.provenance == {}
    assert len(state.outbox_events) == 1
    assert state.outbox_events[0][3]["observation_count"] == 0


@pytest.mark.asyncio
async def test_unit_of_work_closes_after_commit() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresDraftClaimObservationApplicationUnitOfWork(connection)

    await unit_of_work.save_draft_claim_observations((_observation(),))
    await unit_of_work.commit()

    with pytest.raises(DraftClaimObservationUnitOfWorkClosedError):
        await unit_of_work.rollback()


def test_adapter_source_has_no_legacy_or_runtime_infrastructure_dependencies() -> None:
    text = ADAPTER_FILE.read_text(encoding="utf-8")

    forbidden = (
        "SectionBatchQueueItem",
        "CLAIM_OBSERVATIONS_PERSISTED",
        "REGISTRY_APPLICATION",
        "src.infrastructure.",
        "src.contexts.execution_runtime.infrastructure",
        "src.contexts.llm_runtime.infrastructure",
        "src.contexts.artifact_runtime.infrastructure",
        "claim_extraction_stage_blockers",
        "type: ignore",
    )

    offenders = [item for item in forbidden if item in text]

    assert not offenders
