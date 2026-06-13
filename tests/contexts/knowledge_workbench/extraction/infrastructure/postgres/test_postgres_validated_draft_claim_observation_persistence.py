from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    ValidatedDraftClaimObservationCandidate,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_validated_draft_claim_observation_persistence import (
    PostgresValidatedDraftClaimObservationPersistence,
)


@dataclass(slots=True)
class FakeConnection:
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def execute(self, query: str, *args: object) -> object:
        self.calls.append((query, args))
        return "OK"


def _candidate(index: int = 0) -> ValidatedDraftClaimObservationCandidate:
    return ValidatedDraftClaimObservationCandidate(
        workflow_run_id="workflow-1",
        stage_run_id="claim_builder_section_extraction",
        prompt_id="faq_claim_observations",
        prompt_version="v1",
        source_document_ref="source-document-1",
        source_unit_ref="source-unit-1",
        source_unit_ordinal=3,
        work_item_id="work-1",
        dispatch_attempt_id="work-1:attempt-1",
        claim_index=index,
        provider="groq",
        model_ref="qwen/qwen3-32b",
        claim=f"Claim {index}",
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=(f"Question {index}?",),
        exclusion_scope="none",
        evidence_block=f"Evidence {index}",
        validation_decision="VALID_CLAIMS",
    )


@pytest.mark.asyncio
async def test_persists_zero_candidates_as_zero() -> None:
    connection = FakeConnection()

    result = await PostgresValidatedDraftClaimObservationPersistence(
        connection,
    ).persist_validated_claims(())

    assert result.persisted_count == 0
    assert connection.calls == []


@pytest.mark.asyncio
async def test_persists_one_validated_claim_candidate() -> None:
    connection = FakeConnection()

    result = await PostgresValidatedDraftClaimObservationPersistence(
        connection,
    ).persist_validated_claims((_candidate(),))

    assert result.persisted_count == 1
    queries = tuple(query for query, _ in connection.calls)
    assert any("INSERT INTO draft_claim_observations" in query for query in queries)
    assert any(
        "INSERT INTO draft_claim_observation_possible_questions" in query
        for query in queries
    )
    assert any(
        "INSERT INTO draft_claim_observation_provenance" in query for query in queries
    )


@pytest.mark.asyncio
async def test_persists_multiple_candidates() -> None:
    connection = FakeConnection()

    result = await PostgresValidatedDraftClaimObservationPersistence(
        connection,
    ).persist_validated_claims((_candidate(0), _candidate(1)))

    assert result.persisted_count == 2
    observation_inserts = [
        query
        for query, _ in connection.calls
        if "INSERT INTO draft_claim_observations" in query
    ]
    assert len(observation_inserts) == 2


@pytest.mark.asyncio
async def test_persisted_calls_preserve_workflow_source_work_item_dispatch_model_and_evidence_fields() -> (
    None
):
    connection = FakeConnection()
    candidate = _candidate()

    await PostgresValidatedDraftClaimObservationPersistence(
        connection,
    ).persist_validated_claims((candidate,))

    observation_args = next(
        args
        for query, args in connection.calls
        if "INSERT INTO draft_claim_observations" in query
    )
    provenance_args = next(
        args
        for query, args in connection.calls
        if "INSERT INTO draft_claim_observation_provenance" in query
    )

    assert observation_args[1] == candidate.source_unit_ref
    assert observation_args[2] == candidate.claim
    assert observation_args[3] == candidate.granularity.value
    assert observation_args[4] == candidate.exclusion_scope
    assert observation_args[5] == candidate.evidence_block

    assert provenance_args[1] == candidate.source_unit_ref
    assert provenance_args[2] == candidate.workflow_run_id
    assert provenance_args[3] == candidate.stage_run_id
    assert provenance_args[4] == candidate.work_item_id
    assert provenance_args[5] == candidate.dispatch_attempt_id
    assert provenance_args[6] == candidate.work_item_id
    assert provenance_args[7] == candidate.dispatch_attempt_id
    assert provenance_args[8] == candidate.prompt_id
    assert provenance_args[9] == candidate.prompt_version
    assert provenance_args[10] == candidate.claim_index


def test_provenance_schema_and_adapter_do_not_expose_removed_artifact_columns() -> None:
    removed_columns = ("raw_" + "artifact_ref", "parsed_" + "artifact_ref")
    schema_text = Path(
        "migrations/089_create_draft_claim_observation_provenance.sql",
    ).read_text(encoding="utf-8")
    adapter_text = Path(
        "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "postgres_validated_draft_claim_observation_persistence.py",
    ).read_text(encoding="utf-8")

    for column_name in removed_columns:
        assert column_name not in schema_text
        assert column_name not in adapter_text
