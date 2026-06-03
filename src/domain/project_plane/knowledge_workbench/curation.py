from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .errors import DomainInvariantError


class FactCurationSessionStatus(StrEnum):
    OPEN = "open"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class FactCurationChangeKind(StrEnum):
    UPDATE_CLAIM = "update_claim"
    UPDATE_SCOPE = "update_scope"
    UPDATE_EXCLUSION_SCOPE = "update_exclusion_scope"
    UPDATE_QUESTIONS = "update_questions"
    RETIRE_FACT = "retire_fact"


@dataclass(frozen=True, slots=True)
class FactCurationSession:
    session_id: str
    project_id: str
    document_id: str
    fact_registry_id: str
    status: FactCurationSessionStatus

    def __post_init__(self) -> None:
        if not self.session_id:
            raise DomainInvariantError("fact curation session_id is required")
        if not self.fact_registry_id:
            raise DomainInvariantError("fact curation fact_registry_id is required")


@dataclass(frozen=True, slots=True)
class FactCurationChange:
    change_id: str
    session_id: str
    fact_id: str
    change_kind: FactCurationChangeKind
    payload: dict[str, object]

    def __post_init__(self) -> None:
        if not self.change_id:
            raise DomainInvariantError("fact curation change_id is required")
        if not self.fact_id:
            raise DomainInvariantError("fact curation fact_id is required")


def ensure_curation_change_not_runtime_mutation(change: FactCurationChange) -> None:
    if change.change_kind is FactCurationChangeKind.RETIRE_FACT and not change.payload:
        return


__all__ = [
    "FactCurationChange",
    "FactCurationChangeKind",
    "FactCurationSession",
    "FactCurationSessionStatus",
    "ensure_curation_change_not_runtime_mutation",
]
