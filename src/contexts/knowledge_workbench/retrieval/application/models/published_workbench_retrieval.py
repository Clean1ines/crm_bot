from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PublishedWorkbenchRetrievalSourceRef:
    workflow_run_id: str | None
    source_document_ref: str | None
    curation_item_ref: str | None
    source_claim_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_optional_text(self.workflow_run_id, "workflow_run_id")
        _require_optional_text(self.source_document_ref, "source_document_ref")
        _require_optional_text(self.curation_item_ref, "curation_item_ref")
        _require_text_tuple(self.source_claim_refs, "source_claim_refs")


@dataclass(frozen=True, slots=True)
class PublishedWorkbenchRetrievalQuery:
    project_id: str
    query_text: str
    query_embedding: tuple[float, ...]
    embedding_model_id: str
    dimensions: int
    limit: int

    def __post_init__(self) -> None:
        _require_text(self.project_id, "project_id")
        _require_text(self.query_text, "query_text")
        _require_text(self.embedding_model_id, "embedding_model_id")
        if self.dimensions < 1:
            raise ValueError("dimensions must be positive")
        if self.limit < 1:
            raise ValueError("limit must be positive")
        if len(self.query_embedding) != self.dimensions:
            raise ValueError("query_embedding length must match dimensions")
        _require_numeric_sequence(self.query_embedding, "query_embedding")

    @classmethod
    def from_sequence(
        cls,
        *,
        project_id: str,
        query_text: str,
        query_embedding: Sequence[float],
        embedding_model_id: str,
        dimensions: int,
        limit: int,
    ) -> PublishedWorkbenchRetrievalQuery:
        return cls(
            project_id=project_id,
            query_text=query_text,
            query_embedding=tuple(float(value) for value in query_embedding),
            embedding_model_id=embedding_model_id,
            dimensions=dimensions,
            limit=limit,
        )


@dataclass(frozen=True, slots=True)
class PublishedWorkbenchRetrievalResult:
    runtime_entry_id: str
    publication_id: str | None
    project_id: str
    source_document_ref: str | None
    fact_id: str
    curation_item_ref: str | None
    claim: str
    answer_text: str
    possible_questions: tuple[str, ...]
    exclusion_scope: str | None
    evidence_block: str | None
    source_claim_refs: tuple[str, ...]
    embedding_text: str
    score: float
    rank: int
    source_ref: PublishedWorkbenchRetrievalSourceRef

    def __post_init__(self) -> None:
        _require_text(self.runtime_entry_id, "runtime_entry_id")
        _require_optional_text(self.publication_id, "publication_id")
        _require_text(self.project_id, "project_id")
        _require_optional_text(self.source_document_ref, "source_document_ref")
        _require_text(self.fact_id, "fact_id")
        _require_optional_text(self.curation_item_ref, "curation_item_ref")
        _require_text(self.claim, "claim")
        _require_text(self.answer_text, "answer_text")
        _require_text_tuple(self.possible_questions, "possible_questions")
        _require_optional_text(self.exclusion_scope, "exclusion_scope")
        _require_optional_text(self.evidence_block, "evidence_block")
        _require_text_tuple(self.source_claim_refs, "source_claim_refs")
        _require_text(self.embedding_text, "embedding_text")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise TypeError("score must be numeric")
        if self.rank < 1:
            raise ValueError("rank must be positive")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")


def _require_optional_text(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text or None")
    if value != value.strip():
        raise ValueError(f"{field_name} must be stripped")


def _require_text_tuple(value: tuple[str, ...], field_name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be non-empty text")


def _require_numeric_sequence(value: tuple[float, ...], field_name: str) -> None:
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(f"{field_name}[{index}] must be numeric")
