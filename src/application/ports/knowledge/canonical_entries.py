from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_compilation import CanonicalKnowledgeEntry


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRuntimeEntries:
    project_id: str
    document_id: str
    file_name: str
    preprocessing_mode: str
    entries: tuple[CanonicalKnowledgeEntry, ...]


class KnowledgeCanonicalEntryPort(Protocol):
    async def add_canonical_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        entries: Sequence[CanonicalKnowledgeEntry],
    ) -> int: ...

    async def list_document_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[CanonicalKnowledgeEntry, ...]: ...

    async def apply_document_answer_resolution_retightening(
        self,
        *,
        project_id: str,
        document_id: str,
        updated_entries: Sequence[CanonicalKnowledgeEntry],
        archived_entry_ids: Sequence[str],
        metrics: JsonObject,
    ) -> JsonObject: ...

    async def load_document_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeDocumentRuntimeEntries | None: ...
