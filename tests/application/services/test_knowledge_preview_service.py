from __future__ import annotations

import asyncio

from src.application.services.knowledge_preview_retrieval_service import (
    KnowledgePreviewProductionRetrievalService,
)
from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView


class FakeRuntimeRetrieval:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, str, int, bool, str | None]] = []

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]:
        self.search_calls.append((project_id, query, limit, hybrid_fallback, thread_id))
        return [
            KnowledgeSearchResultView(
                id="runtime-1",
                content="Доставка занимает 2-3 дня.",
                score=0.82,
                method="retrieval_surface_hybrid",
                document_id="doc-1",
                source="delivery.md",
                document_status="processed",
            )
        ]


def test_preview_production_retrieval_uses_runtime_equivalent_search() -> None:
    retrieval = FakeRuntimeRetrieval()

    results = asyncio.run(
        KnowledgePreviewProductionRetrievalService(retrieval).search(
            project_id="project-1",
            query="сколько идёт доставка?",
            limit=5,
        )
    )

    assert retrieval.search_calls == [
        ("project-1", "сколько идёт доставка?", 10, True, None)
    ]
    assert results[0].id == "runtime-1"
    assert results[0].method == "retrieval_surface_hybrid"


def test_preview_production_retrieval_doubles_candidate_limit() -> None:
    retrieval = FakeRuntimeRetrieval()

    asyncio.run(
        KnowledgePreviewProductionRetrievalService(retrieval).search(
            project_id="project-1",
            query="возврат",
            limit=7,
        )
    )

    assert retrieval.search_calls == [("project-1", "возврат", 14, True, None)]


def test_preview_production_retrieval_is_not_old_lexical_debug_path() -> None:
    retrieval = FakeRuntimeRetrieval()

    results = asyncio.run(
        KnowledgePreviewProductionRetrievalService(retrieval).search(
            project_id="project-1",
            query="debug",
            limit=3,
        )
    )

    assert retrieval.search_calls == [("project-1", "debug", 6, True, None)]
    assert all(result.method != "retrieval_surface_lexical" for result in results)
