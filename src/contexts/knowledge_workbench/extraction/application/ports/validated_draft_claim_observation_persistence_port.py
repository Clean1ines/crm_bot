from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)


@dataclass(frozen=True, slots=True)
class ValidatedDraftClaimObservationCandidate:
    workflow_run_id: str
    source_document_ref: str | None
    source_unit_ref: str
    source_unit_ordinal: int | None
    work_item_id: str
    dispatch_attempt_id: str
    claim_index: int
    provider: str
    model_ref: str
    claim: str
    granularity: DraftClaimGranularity
    possible_questions: tuple[str, ...]
    exclusion_scope: str
    evidence_block: str
    validation_decision: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        if self.source_document_ref is not None:
            _require_non_empty_text(self.source_document_ref, "source_document_ref")
        _require_non_empty_text(self.source_unit_ref, "source_unit_ref")
        if self.source_unit_ordinal is not None:
            if not isinstance(self.source_unit_ordinal, int):
                raise TypeError("source_unit_ordinal must be int when provided")
            if self.source_unit_ordinal < 0:
                raise ValueError("source_unit_ordinal must be >= 0")
        _require_non_empty_text(self.work_item_id, "work_item_id")
        _require_non_empty_text(self.dispatch_attempt_id, "dispatch_attempt_id")
        if not isinstance(self.claim_index, int):
            raise TypeError("claim_index must be int")
        if self.claim_index < 0:
            raise ValueError("claim_index must be >= 0")
        _require_non_empty_text(self.provider, "provider")
        _require_non_empty_text(self.model_ref, "model_ref")
        _require_non_empty_text(self.claim, "claim")
        if not isinstance(self.granularity, DraftClaimGranularity):
            raise TypeError("granularity must be DraftClaimGranularity")
        if not isinstance(self.possible_questions, tuple):
            raise TypeError("possible_questions must be tuple")
        for question in self.possible_questions:
            _require_non_empty_text(question, "possible_question")
        _require_non_empty_text(self.exclusion_scope, "exclusion_scope")
        _require_non_empty_text(self.evidence_block, "evidence_block")
        _require_non_empty_text(self.validation_decision, "validation_decision")


@dataclass(frozen=True, slots=True)
class PersistValidatedDraftClaimObservationsResult:
    persisted_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.persisted_count, int):
            raise TypeError("persisted_count must be int")
        if self.persisted_count < 0:
            raise ValueError("persisted_count must be >= 0")


class PersistValidatedDraftClaimObservationsPort(Protocol):
    async def persist_validated_claims(
        self,
        candidates: tuple[ValidatedDraftClaimObservationCandidate, ...],
    ) -> PersistValidatedDraftClaimObservationsResult: ...


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
