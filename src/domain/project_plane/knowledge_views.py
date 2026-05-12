from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SourceRefView:
    source_index: int | None = None
    quote: str = ""
    source_chunk_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"quote": self.quote}
        if self.source_index is not None:
            payload["source_index"] = self.source_index
        if self.source_chunk_id is not None:
            payload["source_chunk_id"] = self.source_chunk_id
        if self.start_offset is not None:
            payload["start_offset"] = self.start_offset
        if self.end_offset is not None:
            payload["end_offset"] = self.end_offset
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return payload


def source_refs_from_excerpt(source_excerpt: str | None) -> tuple[SourceRefView, ...]:
    quote = " ".join(str(source_excerpt or "").strip().split())
    if not quote:
        return ()
    return (SourceRefView(source_index=0, quote=quote),)


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResultView:
    id: str
    content: str
    score: float
    method: str
    document_id: str | None = None
    source: str | None = None
    document_status: str | None = None
    entry_kind: str | None = None
    title: str | None = None
    source_excerpt: str | None = None
    source_refs: tuple[SourceRefView, ...] = ()
    embedding_text: str | None = None
    questions: object | None = None
    synonyms: object | None = None
    tags: object | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentView:
    id: str
    file_name: str
    file_size: int | None
    status: str
    error: str | None
    uploaded_by: str | None
    created_at: datetime | str | None
    updated_at: datetime | str | None
    chunk_count: int
    preprocessing_mode: str | None = None
    preprocessing_status: str | None = None
    preprocessing_error: str | None = None
    preprocessing_model: str | None = None
    preprocessing_prompt_version: str | None = None
    preprocessing_metrics: object | None = None
    structured_entries: int = 0
    structured_chunk_count: int = 0


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentDetailView:
    id: str
    project_id: str
    file_name: str
    file_size: int | None
    status: str
    error: str | None
    uploaded_by: str | None
    created_at: datetime | str | None
    updated_at: datetime | str | None
    chunk_count: int
    preprocessing_mode: str | None = None
    preprocessing_status: str | None = None
    preprocessing_error: str | None = None
    preprocessing_model: str | None = None
    preprocessing_prompt_version: str | None = None
    preprocessing_metrics: object | None = None
    structured_entries: int = 0
    structured_chunk_count: int = 0
