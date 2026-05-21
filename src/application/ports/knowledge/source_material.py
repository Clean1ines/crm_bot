from __future__ import annotations

from collections.abc import Sequence
from src.domain.project_plane.knowledge_compilation import SourceChunk
from typing import Protocol


class KnowledgeSourceMaterialPort(Protocol):
    async def add_source_chunks(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: Sequence[SourceChunk],
    ) -> int: ...

    async def list_document_source_chunks(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[SourceChunk, ...]: ...

    async def delete_document_chunks(self, document_id: str) -> None: ...
