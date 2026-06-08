from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)


@dataclass(frozen=True, slots=True)
class SourceDocument:
    document_ref: SourceDocumentRef
    source_format: SourceFormat
    content_hash: str
    created_at: datetime
    original_filename: str | None = None

    def __post_init__(self) -> None:
        if not self.content_hash or not self.content_hash.strip():
            raise ValueError("SourceDocument.content_hash must be non-empty")
        if self.original_filename is not None and not self.original_filename.strip():
            raise ValueError("SourceDocument.original_filename must be non-empty")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("SourceDocument.created_at must be timezone-aware")
