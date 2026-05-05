from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResultView:
    id: str
    content: str
    score: float
    method: str
    document_id: str | None = None
    source: str | None = None
    document_status: str | None = None
    entry_type: str | None = None
    title: str | None = None
    source_excerpt: str | None = None
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
