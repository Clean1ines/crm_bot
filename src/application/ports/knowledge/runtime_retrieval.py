from __future__ import annotations

from src.application.ports.knowledge.documents import KnowledgeDocumentRuntimeEntries
from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView
from typing import Protocol


class KnowledgeRuntimeRetrievalPort(Protocol):
    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]: ...

    async def preview_search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[KnowledgeSearchResultView]: ...

    async def list_runtime_entry_titles(
        self,
        *,
        project_id: str,
        exclude_document_id: str | None = None,
        limit: int = 300,
    ) -> tuple[str, ...]: ...

    async def load_document_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeDocumentRuntimeEntries | None: ...
