from __future__ import annotations

import asyncio
from collections.abc import Mapping

from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView
from src.infrastructure.rag_eval.adapters import (
    RagServiceRagEvalRetriever,
    VectorOnlyRagEvalRetriever,
)


class FakeRagService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []

    async def search_with_expansion(
        self,
        project_id: str,
        query: str,
        thread_id: str | None = None,
        limit_per_query: int | None = None,
        final_limit: int | None = None,
    ) -> list[Mapping[str, object]]:
        self.calls.append((project_id, query, final_limit))
        return [
            {"id": "hybrid-1", "content": "hybrid answer", "score": 0.9},
        ]


class FakeKnowledgeRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, bool, str | None]] = []

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]:
        self.calls.append((project_id, query, limit, hybrid_fallback, thread_id))
        return [
            KnowledgeSearchResultView(
                id="vector-1",
                content="vector answer",
                score=0.8,
                method="vector",
            ),
        ]


def test_production_equivalent_retriever_calls_rag_service_path() -> None:
    service = FakeRagService()

    result = asyncio.run(
        RagServiceRagEvalRetriever(service).retrieve(
            project_id="project-1",
            question="delivery",
            limit=5,
        )
    )

    assert service.calls == [("project-1", "delivery", 5)]
    assert [entry.id for entry in result] == ["hybrid-1"]


def test_vector_debug_retriever_calls_vector_only_search_without_query_expansion() -> (
    None
):
    repo = FakeKnowledgeRepo()

    result = asyncio.run(
        VectorOnlyRagEvalRetriever(repo).retrieve(
            project_id="project-1",
            question="delivery",
            limit=5,
        )
    )

    assert repo.calls == [("project-1", "delivery", 5, False, None)]
    assert [entry.id for entry in result] == ["vector-1"]
