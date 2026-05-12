from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.knowledge_chunk_classification import (
    KnowledgeChunkClassificationInput,
    classify_knowledge_chunk_role,
)
from src.domain.project_plane.knowledge_chunks import (
    KnowledgeChunk,
    KnowledgeChunkDraft,
)
from src.domain.project_plane.knowledge_document_structure import (
    ParsedKnowledgeDocument,
)


@dataclass(frozen=True, slots=True)
class KnowledgeNormalizationResult:
    document: ParsedKnowledgeDocument
    chunks: tuple[KnowledgeChunk, ...]

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    @property
    def answerable_chunks(self) -> tuple[KnowledgeChunk, ...]:
        return tuple(chunk for chunk in self.chunks if chunk.role.is_answerable)


class KnowledgeNormalizationService:
    def normalize_document(
        self,
        document: ParsedKnowledgeDocument,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeNormalizationResult:
        chunks: list[KnowledgeChunk] = []

        for draft in document.chunks:
            normalized = self._normalize_draft(
                draft,
                project_id=project_id,
                document_id=document_id,
            )
            if normalized is None:
                continue
            chunks.append(normalized)

        return KnowledgeNormalizationResult(
            document=document,
            chunks=tuple(chunks),
        )

    def _normalize_draft(
        self,
        draft: KnowledgeChunkDraft,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeChunk | None:
        if not _is_indexable_content(draft.content):
            return None

        section_title = draft.section_path.title
        role = classify_knowledge_chunk_role(
            KnowledgeChunkClassificationInput(
                title=draft.title or section_title,
                header=draft.section_path.leaf,
                body=draft.content,
                parent_title=section_title,
                questions=draft.questions,
                tags=draft.tags,
            )
        )

        classified_draft = draft.with_role(role)

        return KnowledgeChunk.from_draft(
            project_id=project_id,
            document_id=document_id,
            draft=classified_draft,
        )


def _is_indexable_content(value: str) -> bool:
    normalized = " ".join(value.split())

    if len(normalized) < 20:
        return False

    if normalized in {"---", "***", "___", "--", "-"}:
        return False

    return True
