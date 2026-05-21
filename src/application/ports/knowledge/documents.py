from __future__ import annotations

from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_compilation import CanonicalKnowledgeEntry
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode
from src.domain.project_plane.knowledge_views import KnowledgeDocumentDetailView
from typing import Protocol


class KnowledgeDbPoolPort(Protocol):
    """Opaque DB pool passed through to infrastructure repository factories."""


class KnowledgeDocumentRuntimeEntries:
    project_id: str
    document_id: str
    file_name: str
    preprocessing_mode: str
    entries: tuple[CanonicalKnowledgeEntry, ...]


class KnowledgeDocumentPort(Protocol):
    async def create_document(
        self,
        project_id: str,
        file_name: str,
        file_size: int | None = None,
        uploaded_by: str | None = None,
    ) -> str: ...

    async def get_document(
        self,
        document_id: str,
    ) -> KnowledgeDocumentDetailView | None: ...

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None: ...

    async def update_document_preprocessing_status(
        self,
        document_id: str,
        *,
        mode: KnowledgePreprocessingMode,
        status: str,
        error: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: JsonObject | None = None,
    ) -> None: ...

    async def cancel_document_processing(
        self,
        *,
        project_id: str,
        document_id: str,
        reason: str,
    ) -> bool: ...

    async def is_document_processing_cancelled(self, document_id: str) -> bool: ...

    async def clear_project_knowledge(self, project_id: str) -> None: ...
