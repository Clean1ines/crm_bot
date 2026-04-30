from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView
from src.infrastructure.llm.rag_contract import RAGPipelineConfig
from src.infrastructure.llm.rag_service import RAGService


class FakeKnowledgeRepository:
    def __init__(self, responses: dict[str, list[Mapping[str, object]]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
    ) -> list[Mapping[str, object]]:
        self.calls.append(
            {
                "project_id": project_id,
                "query": query,
                "limit": limit,
                "hybrid_fallback": hybrid_fallback,
            }
        )
        return list(self.responses.get(query, []))


class FakeExpander:
    def __init__(self, expansions: list[str]) -> None:
        self.expansions = expansions
        self.calls: list[dict[str, object]] = []

    async def expand(self, query: str, *, max_expansions: int) -> list[str]:
        self.calls.append({"query": query, "max_expansions": max_expansions})
        return self.expansions


class FailingExpander:
    async def expand(self, query: str, *, max_expansions: int) -> list[str]:
        raise RuntimeError("groq unavailable")


@pytest.mark.asyncio
async def test_rag_pipeline_expands_searches_deduplicates_and_reranks_without_groq():
    repo = FakeKnowledgeRepository(
        {
            "crm api": [
                {
                    "id": "chunk-1",
                    "content": "CRM API integration guide",
                    "score": 0.70,
                    "method": "vector",
                },
                {
                    "id": "chunk-2",
                    "content": "Pricing page",
                    "score": 0.95,
                    "method": "vector",
                },
            ],
            "crm integration": [
                {
                    "id": "chunk-1",
                    "content": "CRM API integration guide",
                    "score": 0.90,
                    "method": "fts",
                },
                {
                    "id": "chunk-3",
                    "content": "Webhook and OAuth setup for CRM",
                    "score": 0.80,
                    "method": "hybrid",
                },
            ],
        }
    )
    expander = FakeExpander(["crm integration", "CRM integration", ""])
    service = RAGService(
        repo,
        query_expander=expander,
        config=RAGPipelineConfig(
            limit_per_query=2,
            final_limit=2,
            max_expansions=3,
            max_candidates=10,
            keyword_boost=0.15,
            position_boost=0.05,
        ),
    )

    result = await service.search_with_expansion(
        project_id="project-1",
        query="CRM API",
    )

    assert [call["query"] for call in repo.calls] == ["crm api", "crm integration"]
    assert all(call["limit"] == 2 for call in repo.calls)
    assert all(call["hybrid_fallback"] is True for call in repo.calls)

    assert len(result) == 2
    assert result[0]["id"] == "chunk-1"
    assert result[0]["score"] > 0.90
    assert result[0]["method"] == "fts"


@pytest.mark.asyncio
async def test_rag_pipeline_falls_back_to_original_query_when_expansion_fails():
    repo = FakeKnowledgeRepository(
        {
            "refund policy": [
                {
                    "id": "chunk-1",
                    "content": "Refund policy is available on request",
                    "score": 0.60,
                    "method": "vector",
                }
            ]
        }
    )
    service = RAGService(repo, query_expander=FailingExpander())

    result = await service.search_with_expansion(
        project_id="project-1",
        query="Refund policy",
    )

    assert [call["query"] for call in repo.calls] == ["refund policy"]
    assert result[0]["id"] == "chunk-1"


@pytest.mark.asyncio
async def test_rag_pipeline_enforces_limits_and_candidate_cap():
    rows = [
        {
            "id": f"chunk-{index}",
            "content": f"Relevant CRM chunk {index}",
            "score": 1.0 - index * 0.01,
            "method": "vector",
        }
        for index in range(10)
    ]
    repo = FakeKnowledgeRepository({"crm": rows})
    service = RAGService(
        repo,
        query_expander=FakeExpander([]),
        config=RAGPipelineConfig(
            limit_per_query=5,
            final_limit=3,
            max_candidates=4,
        ),
    )

    result = await service.search_with_expansion(
        project_id="project-1",
        query="crm",
    )

    assert repo.calls[0]["limit"] == 5
    assert len(result) == 3
    assert [item["id"] for item in result] == ["chunk-0", "chunk-1", "chunk-2"]


@pytest.mark.asyncio
async def test_rag_pipeline_returns_empty_for_empty_query_or_missing_project():
    repo = FakeKnowledgeRepository({})
    service = RAGService(repo)

    assert await service.search_with_expansion(project_id="", query="crm") == []
    assert (
        await service.search_with_expansion(project_id="project-1", query="   ") == []
    )
    assert repo.calls == []


@pytest.mark.asyncio
async def test_rag_pipeline_accepts_typed_knowledge_views_from_repository():
    repo = FakeKnowledgeRepository(
        {
            "pricing": [
                KnowledgeSearchResultView(
                    id="chunk-1",
                    content="Pricing and packages overview",
                    score=0.82,
                    method="hybrid",
                    document_id="doc-1",
                    source="pricing.md",
                    document_status="ready",
                )
            ]
        }
    )
    service = RAGService(repo)

    result = await service.search_with_expansion(
        project_id="project-1",
        query="pricing",
    )

    assert result == [
        {
            "id": "chunk-1",
            "content": "Pricing and packages overview",
            "score": pytest.approx(1.02),
            "method": "hybrid",
            "source": "pricing.md",
            "title": None,
            "chunk_index": None,
        }
    ]


def test_safe_json_extract_rejects_non_integer_indexes():
    service = RAGService.__new__(RAGService)

    assert service._safe_json_extract("answer: [1, 2, 3]") == [1, 2, 3]
    assert service._safe_json_extract("answer: [1, 2.5, 3]") == []
    assert service._safe_json_extract("[true, 2]") == []
