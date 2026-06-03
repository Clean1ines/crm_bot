from __future__ import annotations

from src.application.ports.knowledge.runtime_search import (
    KnowledgeRuntimeRetrievalPort,
)
from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView


class KnowledgePreviewProductionRetrievalService:
    """Runtime-equivalent preview adapter over the production retrieval path.

    This intentionally calls KnowledgeRuntimeRetrievalPort.search(), the same
    repository contract used by runtime RAG retrieval. It does not call the
    lexical debug preview path.
    """

    def __init__(self, retrieval: KnowledgeRuntimeRetrievalPort) -> None:
        self._retrieval = retrieval

    async def search(
        self,
        *,
        project_id: str,
        query: str,
        limit: int,
    ) -> list[KnowledgeSearchResultView]:
        return await self._retrieval.search(
            project_id=project_id,
            query=query,
            limit=max(limit * 2, limit),
            hybrid_fallback=True,
        )
