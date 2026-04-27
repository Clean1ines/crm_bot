from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResultView:
    id: str
    content: str
    score: float
    method: str


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
