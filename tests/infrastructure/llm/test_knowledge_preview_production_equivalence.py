from __future__ import annotations

import asyncio

from src.application.services.knowledge_preview_retrieval_service import (
    KnowledgePreviewProductionRetrievalService,
)
from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView
from src.infrastructure.llm.rag_contract import RAGPipelineConfig
from src.infrastructure.llm.rag_service import RAGService


class FakeProductionRepo:
    def __init__(self) -> None:
        self.search_calls: list[str] = []

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]:
        self.search_calls.append(query)
        return [
            KnowledgeSearchResultView(
                id="entry-1",
                content="доставка занимает два дня",
                score=1.0,
                method="retrieval_surface_hybrid",
            ),
            KnowledgeSearchResultView(
                id="entry-2",
                content="самовывоз доступен завтра",
                score=0.8,
                method="retrieval_surface_hybrid",
            ),
        ][:limit]

    async def preview_search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[KnowledgeSearchResultView]:
        raise AssertionError(
            "production-equivalent preview must not use preview_search"
        )


def test_default_preview_and_rag_service_use_same_production_top_ids_without_expansion() -> (
    None
):
    repo = FakeProductionRepo()
    query = "доставка"
    limit = 2

    preview_results = asyncio.run(
        KnowledgePreviewProductionRetrievalService(repo).search(
            project_id="project-1",
            query=query,
            limit=limit,
        )
    )
    rag_results = asyncio.run(
        RAGService(
            repo,
            config=RAGPipelineConfig(
                limit_per_query=limit,
                final_limit=limit,
                max_expansions=0,
                max_candidates=limit,
                keyword_boost=0.0,
                position_boost=0.0,
            ),
        ).search_with_expansion(
            project_id="project-1",
            query=query,
            limit_per_query=limit,
            final_limit=limit,
        )
    )

    assert [item.id for item in preview_results[:limit]] == [
        str(item["id"]) for item in rag_results
    ]
