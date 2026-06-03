from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView


class KnowledgeRuntimeRetrievalPort(Protocol):
    """Search-only runtime retrieval port for preview/RAG-safe consumers.

    Safe read paths that only need production search must depend on this narrow
    port instead of the old broad runtime retrieval contract.
    """

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]: ...


__all__ = ["KnowledgeRuntimeRetrievalPort"]
