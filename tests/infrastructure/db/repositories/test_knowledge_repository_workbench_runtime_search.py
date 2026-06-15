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

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        del args
        self.queries.append(query)
        return self.rows


def _row() -> dict[str, object]:
    return {
        "id": "runtime-entry-1",
        "content": "Claim text from Workbench runtime.",
        "document_id": "source-document:1",
        "source": "source-document:1",
        "document_status": "active",
        "entry_kind": "faq_workbench_fact",
        "title": None,
        "source_refs": [{"quote": "quote from source claim"}],
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
        assert (
            "knowledge_workbench_runtime_retrieval_entry_embeddings" in query
            or query == RUNTIME_PREVIEW_SEARCH_SQL
        )
        assert "knowledge_workbench_canonical_facts" in query
        assert "entry.claim AS content" in query
        assert "entry.possible_questions AS questions" in query
        assert "knowledge_" + "retrieval_" + "surface" not in query
        assert "rs.answer" not in query
        assert "rs." + "enrichment" not in query


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
    assert results[0].questions == ["Question?"]
    assert results[0].source_refs[0].quote == "quote from source claim"
    assert results[0].method in {"hybrid", "vector", "fts"}
    assert "knowledge_workbench_runtime_retrieval_entries" in connection.queries[0]


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
    assert "knowledge_workbench_runtime_retrieval_entries" in connection.queries[0]
