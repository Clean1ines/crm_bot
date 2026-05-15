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
class KnowledgeSearchTraceView:
    matched_fields: tuple[str, ...] = ()
    lexical_score: float = 0.0
    vector_score: float = 0.0
    exact_question_match: bool = False
    title_match: bool = False
    length_penalty: float = 0.0
    final_score: float = 0.0
    retrieval_surface_role: str = "runtime"
    displayed_field: str = "answer"
    is_production_safe: bool = True


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
    trace: KnowledgeSearchTraceView | None = None


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
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0
    llm_tokens_total: int = 0
    llm_usage_events_count: int = 0
    llm_models: str = ""


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
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0
    llm_tokens_total: int = 0
    llm_usage_events_count: int = 0
    llm_models: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeCompilerBatchView:
    id: str
    compiler_run_id: str
    batch_index: int
    batch_count: int
    status: str
    source_chunk_ids: object
    source_chunk_indexes: object
    attempt_count: int = 0
    model: str = ""
    prompt_version: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    error_type: str = ""
    error_message: str = ""
    started_at: datetime | str | None = None
    finished_at: datetime | str | None = None
    updated_at: datetime | str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerCandidateSummaryView:
    total_count: int = 0
    raw_count: int = 0
    final_count: int = 0
    rejected_count: int = 0
    grounded_count: int = 0
