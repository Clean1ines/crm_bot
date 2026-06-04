from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import pytest

from src.application.services.faq_workbench_local_claim_retrieval_service import (
    LoadIndexedLocalClaimRetrievalSurfaceCommand,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class NoopTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


@dataclass(slots=True)
class CapturingConnection:
    fetch_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def transaction(self) -> NoopTransaction:
        return NoopTransaction()

    async def execute(self, query: str, *args: object) -> str:
        raise AssertionError(f"unexpected execute: {query} {args}")

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        raise AssertionError(f"unexpected fetchrow: {query} {args}")

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> Sequence[Mapping[str, object]]:
        normalized_query = " ".join(query.lower().split())
        self.fetch_calls.append((normalized_query, args))
        if "left_entry.embedding <=> right_entry.embedding" in normalized_query:
            return (
                {
                    "source_search_document_id": "section-1:node-1:c1",
                    "target_search_document_id": "section-2:node-2:c2",
                    "score": 0.93,
                },
            )
        if "select search_document_id, project_id, document_id" in normalized_query:
            return (
                {
                    "search_document_id": "section-1:node-1:c1",
                    "project_id": "project-1",
                    "document_id": "document-1",
                    "section_id": "section-1",
                    "node_run_id": "node-1",
                    "local_ref": "c1",
                    "claim": "Бот отвечает клиентам.",
                    "claim_kind": "capability",
                    "granularity": "atomic",
                    "triples_payload": ["бот отвечает клиентам"],
                    "possible_questions_payload": ["Может ли бот отвечать?"],
                    "scope": "Telegram",
                    "exclusion_scope": "",
                    "evidence_block": "Бот отвечает клиентам.",
                    "relation_texts_payload": [],
                    "search_text": "claim: Бот отвечает клиентам.",
                },
                {
                    "search_document_id": "section-2:node-2:c2",
                    "project_id": "project-1",
                    "document_id": "document-1",
                    "section_id": "section-2",
                    "node_run_id": "node-2",
                    "local_ref": "c2",
                    "claim": "AI-ассистент отвечает покупателям.",
                    "claim_kind": "capability",
                    "granularity": "atomic",
                    "triples_payload": [],
                    "possible_questions_payload": ["Где ассистент отвечает?"],
                    "scope": "Telegram",
                    "exclusion_scope": "",
                    "evidence_block": "AI-ассистент отвечает покупателям.",
                    "relation_texts_payload": [],
                    "search_text": "claim: AI-ассистент отвечает покупателям.",
                },
            )
        raise AssertionError(f"unexpected fetch query: {query}")


@pytest.mark.asyncio
async def test_load_indexed_local_claim_retrieval_surface_reads_documents_and_vector_edges() -> (
    None
):
    connection = CapturingConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    result = await repository.load_indexed_local_claim_retrieval_surface(
        LoadIndexedLocalClaimRetrievalSurfaceCommand(
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="document-1",
            processing_run_id="run-1",
            min_vector_similarity_score=0.72,
            max_candidates_per_claim=20,
        )
    )

    assert result.indexed_claim_count == 2
    assert len(result.vector_similarity_edges) == 1
    assert result.vector_similarity_edges[0].signals[0].signal_type == (
        "embedding_similarity"
    )
    assert result.search_documents[0].possible_questions == ("Может ли бот отвечать?",)

    assert len(connection.fetch_calls) == 2
    document_query, document_args = connection.fetch_calls[0]
    edge_query, edge_args = connection.fetch_calls[1]

    assert "from knowledge_workbench_local_claim_retrieval_entries" in document_query
    assert "status = 'indexed'" in document_query
    assert "order by section_id asc, node_run_id asc, local_ref asc" in document_query
    assert document_args == (
        "00000000-0000-0000-0000-000000000001",
        "document-1",
        "run-1",
    )

    assert "join lateral" in edge_query
    assert "left_entry.embedding <=> right_entry.embedding" in edge_query
    assert "limit $4" in edge_query
    assert "where score >= $5" in edge_query
    assert edge_args == (
        "00000000-0000-0000-0000-000000000001",
        "document-1",
        "run-1",
        20,
        0.72,
    )
