from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DraftClaimObservationReadModel:
    observation_ref: str
    source_unit_ref: str
    claim: str
    granularity: str
    possible_questions: tuple[str, ...]
    exclusion_scope: str
    evidence_block: str
    workflow_run_id: str | None
    stage_run_id: str | None
    work_item_id: str | None
    work_item_attempt_id: str | None
    llm_task_id: str | None
    llm_attempt_id: str | None
    prompt_id: str | None
    prompt_version: str | None
    claim_index: int | None
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.observation_ref, "observation_ref")
        _require_non_empty_text(self.source_unit_ref, "source_unit_ref")
        _require_non_empty_text(self.claim, "claim")
        _require_non_empty_text(self.granularity, "granularity")
        if not isinstance(self.possible_questions, tuple):
            raise TypeError("possible_questions must be tuple")
        for question in self.possible_questions:
            _require_non_empty_text(question, "possible_question")
        if not isinstance(self.exclusion_scope, str):
            raise TypeError("exclusion_scope must be str")
        _require_non_empty_text(self.evidence_block, "evidence_block")
        for field_name in (
            "workflow_run_id",
            "stage_run_id",
            "work_item_id",
            "work_item_attempt_id",
            "llm_task_id",
            "llm_attempt_id",
            "prompt_id",
            "prompt_version",
        ):
            _require_optional_text(getattr(self, field_name), field_name)
        if self.claim_index is not None:
            if not isinstance(self.claim_index, int):
                raise TypeError("claim_index must be int when provided")
            if self.claim_index < 0:
                raise ValueError("claim_index must be >= 0")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")


class DraftClaimObservationReadRepositoryPort(Protocol):
    async def list_by_source_document_ref(
        self,
        *,
        source_document_ref: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimObservationReadModel, ...]: ...

    async def list_by_source_unit_ref(
        self,
        *,
        source_unit_ref: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimObservationReadModel, ...]: ...


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_text(value: str | None, field_name: str) -> None:
    if value is None:
        return
    _require_non_empty_text(value, field_name)
