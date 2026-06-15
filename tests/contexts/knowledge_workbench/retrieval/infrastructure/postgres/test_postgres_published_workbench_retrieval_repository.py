from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pytest

from src.contexts.knowledge_workbench.retrieval.infrastructure.postgres.postgres_published_workbench_retrieval_repository import (
    PUBLISHED_WORKBENCH_VECTOR_SEARCH_SQL,
    PostgresPublishedWorkbenchRetrievalRepository,
)


class FetchConnection(Protocol):
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]: ...


@dataclass(slots=True)
class FakeConnection:
    query: str | None = None
    args: tuple[object, ...] | None = None
    rows: list[dict[str, object]] = field(default_factory=list)

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.query = query
        self.args = args
        return self.rows


def _row(
    *, project_id: str = "11111111-1111-1111-1111-111111111111"
) -> dict[str, object]:
    return {
        "runtime_entry_id": "runtime-entry-1",
        "publication_id": "draft-claim-curation-publication:workflow-1",
        "project_id": project_id,
        "fact_id": "fact-1",
        "claim": "Published compacted claim",
        "answer_text": "Published compacted claim",
        "possible_questions": ["Question one?", "Question two?"],
        "embedding_text": "Claim:\\nPublished compacted claim",
        "source_refs": {
            "workflow_run_id": "workflow-1",
            "source_document_ref": "source-document-1",
            "curation_item_ref": "item-1",
            "source_claim_refs": ["raw-1", "raw-2"],
        },
        "workflow_run_id": "workflow-1",
        "source_document_ref": "source-document-1",
        "curation_item_ref": "item-1",
        "source_claim_refs": ["raw-1", "raw-2"],
        "exclusion_scope": "Not for internal policy",
        "evidence_block": None,
        "score": 0.875,
        "rank": 1,
    }


@pytest.mark.asyncio
async def test_postgres_adapter_fetches_new_published_projection_only() -> None:
    connection = FakeConnection(rows=[_row()])
    repository = PostgresPublishedWorkbenchRetrievalRepository(connection)

    results = await repository.search(
        project_id="11111111-1111-1111-1111-111111111111",
        query_text="question",
        query_embedding=(0.1, 0.2, 0.3),
        embedding_model_id="model-384",
        dimensions=3,
        limit=7,
    )

    assert connection.query == PUBLISHED_WORKBENCH_VECTOR_SEARCH_SQL
    assert connection.args == (
        "11111111-1111-1111-1111-111111111111",
        "model-384",
        3,
        "[0.1,0.2,0.3]",
        7,
    )
    assert results[0].runtime_entry_id == "runtime-entry-1"
    assert results[0].publication_id == "draft-claim-curation-publication:workflow-1"
    assert results[0].fact_id == "fact-1"
    assert results[0].possible_questions == ("Question one?", "Question two?")
    assert results[0].source_claim_refs == ("raw-1", "raw-2")
    assert results[0].source_ref.workflow_run_id == "workflow-1"


def test_sql_uses_runtime_entry_embeddings_and_filters_runtime_visibility() -> None:
    sql = PUBLISHED_WORKBENCH_VECTOR_SEARCH_SQL

    assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in sql
    assert "knowledge_workbench_runtime_retrieval_entries" in sql
    assert "knowledge_workbench_canonical_facts" in sql
    assert "knowledge_retrieval_surface" not in sql
    assert "knowledge_workbench_surfaces" not in sql
    assert "entry.project_id = $1::uuid" in sql
    assert "entry.visibility = 'published'" in sql
    assert "entry.status = 'active'" in sql
    assert "fact.status = 'published'" in sql
    assert "emb.embedding_model_id = $2" in sql
    assert "emb.dimensions = $3" in sql
    assert "emb.embedding <=> $4::vector" in sql


def test_adapter_source_does_not_import_old_runtime_repository() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/retrieval/infrastructure/postgres/"
        "postgres_published_workbench_retrieval_repository.py"
    ).read_text(encoding="utf-8")

    assert "KnowledgeRepository" not in source
    assert "knowledge_search_queries" not in source
    assert "knowledge_retrieval_surface" not in source
    assert "knowledge_workbench_surfaces" not in source
