from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.knowledge_search_queries import (
    RUNTIME_HYBRID_SEARCH_SQL,
    RUNTIME_PREVIEW_SEARCH_SQL,
    RUNTIME_VECTOR_SEARCH_SQL,
)


@dataclass(slots=True)
class _AcquireContext:
    connection: "_Connection"

    async def __aenter__(self) -> "_Connection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


@dataclass(slots=True)
class _Pool:
    connection: "_Connection"

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self.connection)


@dataclass(slots=True)
class _EmbeddingPort:
    async def embed(
        self, request: EmbeddingGenerationRequest
    ) -> EmbeddingGenerationResult:
        return EmbeddingGenerationResult(
            embeddings=(tuple(0.01 for _ in range(request.expected_dimensions)),),
            model_id=request.model_id,
            dimensions=request.expected_dimensions,
        )


class _Settings:
    local_model = "test-embedding-model"
    vector_dimensions = 384


class _Connection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.queries: list[str] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.queries.append(query)
        self.calls.append((query, args))
        return self.rows


def _row() -> dict[str, object]:
    return {
        "id": "runtime-entry-1",
        "content": "Claim text from Workbench runtime.",
        "document_id": "source-document:1",
        "source": "source-document:1",
        "document_status": "active",
        "entry_kind": "faq_workbench_fact",
        "granularity": "atomic",
        "curation_item_ref": "curation-item-1",
        "exclusion_scope": "Not for internal-only policy",
        "evidence_block": "Evidence from source",
        "triples": [{"subject": "A", "predicate": "related_to", "object": "B"}],
        "title": None,
        "source_refs": [{"quote": "quote from source claim"}],
        "raw_source_refs": {"source_claim_refs": ["raw-1"]},
        "source_claim_refs": ["raw-1"],
        "embedding_text": "Claim text from Workbench runtime. Question?",
        "questions": ["Question?"],
        "synonyms": [],
        "tags": [],
        "search_text": "Claim text from Workbench runtime. Question?",
        "vector_score": 0.9,
        "lexical_score": 0.4,
        "exact_score": 0.0,
        "score": 1.0,
    }


def test_runtime_search_sql_reads_workbench_runtime_tables() -> None:
    for query in (
        RUNTIME_VECTOR_SEARCH_SQL,
        RUNTIME_HYBRID_SEARCH_SQL,
        RUNTIME_PREVIEW_SEARCH_SQL,
    ):
        assert "knowledge_workbench_runtime_retrieval_entries" in query
        assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in query
        assert "knowledge_workbench_canonical_facts" not in query
        assert "fact.status" not in query
        assert "entry.project_id =" in query
        assert "entry.visibility = 'published'" in query
        assert "entry.status = 'active'" in query
        assert "entry.claim AS content" in query
        assert "entry.possible_questions AS questions" in query
        assert "entry.claim_kind" in query
        assert "entry.granularity" in query
        assert "entry.exclusion_scope" in query
        assert "entry.evidence_block" in query
        assert "entry.triples" in query
        assert "entry.source_document_ref" in query
        assert "entry.source_claim_refs" in query
        assert "entry.source_refs AS raw_source_refs" in query
        assert "entry.embedding_text" in query
        assert "knowledge_" + "retrieval_" + "surface" not in query
        assert "rs.answer" not in query
        assert "rs." + "enrichment" not in query


def test_runtime_search_positive_text_excludes_exclusion_scope() -> None:
    for query in (
        RUNTIME_VECTOR_SEARCH_SQL,
        RUNTIME_HYBRID_SEARCH_SQL,
        RUNTIME_PREVIEW_SEARCH_SQL,
    ):
        assert "entry.exclusion_scope" in query
        assert "COALESCE(NULLIF(entry.exclusion_scope" not in query
        assert "COALESCE(entry.exclusion_scope" not in query
        assert "fact.exclusion_scope" not in query


@pytest.mark.asyncio
async def test_search_maps_workbench_claim_to_public_result_content() -> None:
    connection = _Connection([_row()])
    repository = KnowledgeRepository(
        _Pool(connection),
        embedding_generation_port=_EmbeddingPort(),
        embedding_runtime_settings=_Settings(),
    )

    results = await repository.search(
        "11111111-1111-1111-1111-111111111111", "Question?", limit=1
    )

    assert results[0].id == "runtime-entry-1"
    assert results[0].content == "Claim text from Workbench runtime."
    assert results[0].entry_kind == "faq_workbench_fact"
    assert results[0].granularity == "atomic"
    assert results[0].curation_item_ref == "curation-item-1"
    assert results[0].exclusion_scope == "Not for internal-only policy"
    assert results[0].evidence_block == "Evidence from source"
    assert results[0].triples == [
        {"subject": "A", "predicate": "related_to", "object": "B"}
    ]
    assert results[0].questions == ["Question?"]
    assert results[0].document_id == "source-document:1"
    assert results[0].source_claim_refs == ["raw-1"]
    assert results[0].raw_source_refs == {"source_claim_refs": ["raw-1"]}
    assert results[0].embedding_text == "Claim text from Workbench runtime. Question?"
    assert results[0].source_refs[0].quote == "quote from source claim"
    assert results[0].method in {"hybrid", "vector", "fts"}
    assert "knowledge_workbench_runtime_retrieval_entries" in connection.queries[0]
    assert "knowledge_workbench_canonical_facts" not in connection.queries[0]
    assert "emb.embedding_model_id = $7" in connection.queries[0]
    assert "emb.dimensions = $8" in connection.queries[0]
    assert connection.calls[0][1][-2:] == ("test-embedding-model", 384)


@pytest.mark.asyncio
async def test_preview_search_uses_workbench_runtime_lexical_method() -> None:
    connection = _Connection([_row()])
    repository = KnowledgeRepository(
        _Pool(connection),
        embedding_generation_port=_EmbeddingPort(),
        embedding_runtime_settings=_Settings(),
    )

    results = await repository.preview_search(
        "11111111-1111-1111-1111-111111111111",
        "Question?",
        limit=1,
    )

    assert results[0].content == "Claim text from Workbench runtime."
    assert results[0].method == "workbench_runtime_lexical"
    assert results[0].questions == ["Question?"]
    assert results[0].exclusion_scope == "Not for internal-only policy"
    assert results[0].evidence_block == "Evidence from source"
    assert results[0].triples == [
        {"subject": "A", "predicate": "related_to", "object": "B"}
    ]
    assert "knowledge_workbench_runtime_retrieval_entries" in connection.queries[0]
    assert "knowledge_workbench_canonical_facts" not in connection.queries[0]
