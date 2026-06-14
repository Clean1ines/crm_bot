from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DraftClaimEmbeddingCandidate:
    workflow_run_id: str
    source_document_ref: str
    source_unit_ref: str
    observation_ref: str
    embedding_text: str
    embedding_text_hash: str
    embedding_model_id: str
    dimensions: int
    vector: tuple[float, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.source_document_ref, "source_document_ref")
        _require_non_empty_text(self.source_unit_ref, "source_unit_ref")
        _require_non_empty_text(self.observation_ref, "observation_ref")
        _require_non_empty_text(self.embedding_text, "embedding_text")
        _require_non_empty_text(self.embedding_text_hash, "embedding_text_hash")
        _require_non_empty_text(self.embedding_model_id, "embedding_model_id")
        if not isinstance(self.dimensions, int):
            raise TypeError("dimensions must be int")
        if self.dimensions < 1:
            raise ValueError("dimensions must be positive")
        if not isinstance(self.vector, tuple):
            raise TypeError("vector must be tuple")
        if len(self.vector) != self.dimensions:
            raise ValueError("vector length must match dimensions")
        for index, value in enumerate(self.vector):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"vector[{index}] must be numeric")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class PersistDraftClaimEmbeddingsResult:
    requested_count: int
    inserted_count: int
    already_exists_count: int

    def __post_init__(self) -> None:
        _require_non_negative_int(self.requested_count, "requested_count")
        _require_non_negative_int(self.inserted_count, "inserted_count")
        _require_non_negative_int(self.already_exists_count, "already_exists_count")
        if self.inserted_count + self.already_exists_count != self.requested_count:
            raise ValueError(
                "inserted_count + already_exists_count must equal requested_count"
            )


class DraftClaimEmbeddingPersistencePort(Protocol):
    async def persist_draft_claim_embeddings(
        self,
        candidates: tuple[DraftClaimEmbeddingCandidate, ...],
    ) -> PersistDraftClaimEmbeddingsResult: ...


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
