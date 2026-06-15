from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SourceRefView:
    source_index: int | None = None
    quote: str = ""
    source_unit_ref: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"quote": self.quote}
        if self.source_index is not None:
            payload["source_index"] = self.source_index
        if self.source_unit_ref is not None:
            payload["source_unit_ref"] = self.source_unit_ref
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
    displayed_field: str = "claim"
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
    preprocessing_mode: str | None = None
    preprocessing_status: str | None = None
    preprocessing_error: str | None = None
    preprocessing_model: str | None = None
    preprocessing_prompt_version: str | None = None
    preprocessing_metrics: object | None = None
    source_unit_count: int = 0
    draft_claim_count: int = 0
    draft_claim_embedding_count: int = 0
    curated_item_count: int = 0
    runtime_entry_count: int = 0
    runtime_embedding_count: int = 0
    publication_count: int = 0
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
    preprocessing_mode: str | None = None
    preprocessing_status: str | None = None
    preprocessing_error: str | None = None
    preprocessing_model: str | None = None
    preprocessing_prompt_version: str | None = None
    preprocessing_metrics: object | None = None
    source_unit_count: int = 0
    draft_claim_count: int = 0
    draft_claim_embedding_count: int = 0
    curated_item_count: int = 0
    runtime_entry_count: int = 0
    runtime_embedding_count: int = 0
    publication_count: int = 0
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0
    llm_tokens_total: int = 0
    llm_usage_events_count: int = 0
    llm_models: str = ""
