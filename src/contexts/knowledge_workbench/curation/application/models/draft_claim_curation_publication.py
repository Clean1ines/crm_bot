from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.project_plane.json_types import JsonObject


@dataclass(frozen=True, slots=True)
class DraftClaimCurationPublicationItem:
    item_ref: str
    fact_id: str
    runtime_entry_id: str
    claim: str
    claim_kind: str
    granularity: str
    possible_questions: tuple[str, ...]
    exclusion_scope: str
    evidence_block: str
    source_claim_refs: tuple[str, ...]
    triples: tuple[JsonObject, ...]
    embedding_text: str
    embedding_text_hash: str
    embedding_model_id: str
    embedding_dimensions: int
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        _require_text(self.item_ref, "item_ref")
        _require_text(self.fact_id, "fact_id")
        _require_text(self.runtime_entry_id, "runtime_entry_id")
        _require_text(self.claim, "claim")
        _require_text(self.claim_kind, "claim_kind")
        _require_text(self.granularity, "granularity")
        _require_text(self.evidence_block, "evidence_block")
        _require_text(self.embedding_text, "embedding_text")
        _require_text(self.embedding_text_hash, "embedding_text_hash")
        _require_text(self.embedding_model_id, "embedding_model_id")
        if self.embedding_dimensions < 1:
            raise ValueError("embedding_dimensions must be positive")
        if len(self.vector) != self.embedding_dimensions:
            raise ValueError("vector dimensions must match embedding_dimensions")
        for index, value in enumerate(self.vector):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"vector[{index}] must be numeric")
        _require_text_tuple(self.possible_questions, "possible_questions")
        _require_text_tuple(self.source_claim_refs, "source_claim_refs")
        if not isinstance(self.triples, tuple):
            raise TypeError("triples must be tuple")
        for triple in self.triples:
            if not isinstance(triple, dict):
                raise TypeError("triples must contain objects")


@dataclass(frozen=True, slots=True)
class DraftClaimCurationPublicationCandidate:
    publication_id: str
    workflow_run_id: str
    project_id: str
    source_document_ref: str
    fact_registry_id: str
    items: tuple[DraftClaimCurationPublicationItem, ...]
    excluded_item_count: int
    published_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.publication_id, "publication_id")
        _require_text(self.workflow_run_id, "workflow_run_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.source_document_ref, "source_document_ref")
        _require_text(self.fact_registry_id, "fact_registry_id")
        if not self.items:
            raise ValueError("items must be non-empty")
        if self.excluded_item_count < 0:
            raise ValueError("excluded_item_count must be non-negative")
        if not isinstance(self.published_at, datetime):
            raise TypeError("published_at must be datetime")


@dataclass(frozen=True, slots=True)
class DraftClaimCurationPublicationResult:
    status: str
    publication_id: str
    workflow_run_id: str
    project_id: str
    source_document_ref: str
    published_item_count: int
    excluded_item_count: int
    runtime_entry_count: int
    embedding_count: int
    deleted_draft_embedding_count: int
    automatic_processing_elapsed_seconds: int | None
    published_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.status, "status")
        _require_text(self.publication_id, "publication_id")
        _require_text(self.workflow_run_id, "workflow_run_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.source_document_ref, "source_document_ref")
        _require_non_negative(self.published_item_count, "published_item_count")
        _require_non_negative(self.excluded_item_count, "excluded_item_count")
        _require_non_negative(self.runtime_entry_count, "runtime_entry_count")
        _require_non_negative(self.embedding_count, "embedding_count")
        _require_non_negative(
            self.deleted_draft_embedding_count,
            "deleted_draft_embedding_count",
        )
        if (
            self.automatic_processing_elapsed_seconds is not None
            and self.automatic_processing_elapsed_seconds < 0
        ):
            raise ValueError(
                "automatic_processing_elapsed_seconds must be non-negative"
            )
        if not isinstance(self.published_at, datetime):
            raise TypeError("published_at must be datetime")

    def to_json_dict(self) -> JsonObject:
        return {
            "status": self.status,
            "publication_id": self.publication_id,
            "workflow_run_id": self.workflow_run_id,
            "project_id": self.project_id,
            "source_document_ref": self.source_document_ref,
            "published_item_count": self.published_item_count,
            "excluded_item_count": self.excluded_item_count,
            "runtime_entry_count": self.runtime_entry_count,
            "embedding_count": self.embedding_count,
            "deleted_draft_embedding_count": self.deleted_draft_embedding_count,
            "automatic_processing_elapsed_seconds": (
                self.automatic_processing_elapsed_seconds
            ),
            "published_at": self.published_at.isoformat(),
        }


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_text_tuple(value: tuple[str, ...], field_name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be non-empty")


def _require_non_negative(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
