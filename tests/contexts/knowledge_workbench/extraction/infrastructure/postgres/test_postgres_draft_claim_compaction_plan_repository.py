from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchCandidate,
    DraftClaimCompactionBatchForDispatch,
    DraftClaimCompactionEdgeCandidate,
    DraftClaimCompactionGroupCandidate,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_compaction_plan_repository import (
    PostgresDraftClaimCompactionPlanRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _claim_row() -> Mapping[str, object]:
    return {
        "embedding_ref": "embedding-a",
        "workflow_run_id": "workflow-1",
        "source_document_ref": "document-1",
        "source_unit_ref": "unit-1",
        "observation_ref": "claim-a",
        "embedding_text": "Product supports refunds",
        "embedding_model_id": "openai/gpt-oss-120b",
        "dimensions": 2,
        "embedding": "[1,0]",
        "claim": "Product supports refunds",
        "granularity": "atomic",
        "exclusion_scope": "",
        "possible_questions": ["Does product support refunds?"],
        "claim_index": 0,
    }


@dataclass(slots=True)
class FakeConnection:
    executed: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        if "SELECT b.batch_ref" in query:
            assert args == ("batch-1",)
            return [
                {
                    "batch_ref": "batch-1",
                    "workflow_run_id": "workflow-1",
                    "group_ref": "group-1",
                    "prompt_variant": "draft_vs_draft",
                    "model_id": "openai/gpt-oss-120b",
                    "estimated_input_tokens": 100,
                    "member_observation_refs": ["claim-a"],
                }
            ]

        if (
            "SELECT e.embedding_ref" in query
            and "FROM draft_claim_compaction_batches b" in query
        ):
            assert args == ("batch-1",)
            return [_claim_row()]

        assert "draft_claim_embeddings" in query
        assert args == ("workflow-1", "openai/gpt-oss-120b")
        return [_claim_row()]

    async def execute(self, query: str, *args: object) -> object:
        self.executed.append((query, args))
        return "INSERT 0 1"


def _edge() -> DraftClaimCompactionEdgeCandidate:
    return DraftClaimCompactionEdgeCandidate(
        edge_ref="edge-1",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        left_observation_ref="claim-a",
        right_observation_ref="claim-b",
        left_embedding_ref="embedding-a",
        right_embedding_ref="embedding-b",
        vector_score=1.0,
        lexical_score=1.0,
        question_overlap_score=1.0,
        exclusion_scope_score=0.5,
        granularity_score=1.0,
        combined_score=0.98,
        signals={"algorithm": "test"},
    )


def _group() -> DraftClaimCompactionGroupCandidate:
    return DraftClaimCompactionGroupCandidate(
        group_ref="group-1",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        embedding_model_id="openai/gpt-oss-120b",
        group_algorithm="test",
        group_threshold=0.78,
        member_observation_refs=("claim-a", "claim-b"),
        member_embedding_refs=("embedding-a", "embedding-b"),
        member_source_unit_refs=("unit-1", "unit-2"),
        estimated_input_tokens=100,
        requires_split=False,
    )


def _batch() -> DraftClaimCompactionBatchCandidate:
    return DraftClaimCompactionBatchCandidate(
        batch_ref="batch-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        prompt_variant="draft_vs_draft",
        model_id="openai/gpt-oss-120b",
        estimated_input_tokens=100,
        member_observation_refs=("claim-a", "claim-b"),
    )


@pytest.mark.asyncio
async def test_reads_claims_for_compaction_from_joined_rows() -> None:
    repository = PostgresDraftClaimCompactionPlanRepository(FakeConnection())

    claims = await repository.list_claims_for_compaction(
        workflow_run_id="workflow-1",
        embedding_model_id="openai/gpt-oss-120b",
    )

    assert len(claims) == 1
    assert claims[0].observation_ref == "claim-a"
    assert claims[0].possible_questions == ("Does product support refunds?",)
    assert claims[0].vector == (1.0, 0.0)


@pytest.mark.asyncio
async def test_persists_edges_groups_members_and_batches_idempotently() -> None:
    connection = FakeConnection()
    repository = PostgresDraftClaimCompactionPlanRepository(connection)

    result = await repository.persist_compaction_plan(
        edges=(_edge(),),
        groups=(_group(),),
        batches=(_batch(),),
        created_at=_now(),
    )

    assert result.requested_edge_count == 1
    assert result.inserted_edge_count == 1
    assert result.requested_group_count == 1
    assert result.inserted_group_count == 1
    assert result.requested_member_count == 2
    assert result.inserted_member_count == 2
    assert result.requested_batch_count == 1
    assert result.inserted_batch_count == 1
    assert result.already_exists_count == 0
    assert len(connection.executed) == 5
    assert all("ON CONFLICT" in query for query, _ in connection.executed)


@pytest.mark.asyncio
async def test_get_compaction_batch_by_ref_returns_batch() -> None:
    repository = PostgresDraftClaimCompactionPlanRepository(FakeConnection())

    batch = await repository.get_compaction_batch_by_ref(batch_ref="batch-1")

    assert isinstance(batch, DraftClaimCompactionBatchForDispatch)
    assert batch.batch_ref == "batch-1"
    assert batch.workflow_run_id == "workflow-1"
    assert batch.group_ref == "group-1"
    assert batch.prompt_variant == "draft_vs_draft"
    assert batch.model_id == "openai/gpt-oss-120b"
    assert batch.member_observation_refs == ("claim-a",)


@pytest.mark.asyncio
async def test_list_claims_for_compaction_batch_returns_batch_member_claims() -> None:
    repository = PostgresDraftClaimCompactionPlanRepository(FakeConnection())

    claims = await repository.list_claims_for_compaction_batch(batch_ref="batch-1")

    assert len(claims) == 1
    assert claims[0].observation_ref == "claim-a"
    assert claims[0].possible_questions == ("Does product support refunds?",)
