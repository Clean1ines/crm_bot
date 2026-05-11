from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.knowledge_document_structure import (
    ParsedKnowledgeDocument,
)


class KnowledgeDocumentParserPort(Protocol):
    async def parse(
        self,
        *,
        file_bytes: bytes | bytearray,
        filename: str,
        content_type: str | None = None,
    ) -> ParsedKnowledgeDocument: ...
