from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .shared import DomainInvariantError, FactId, JsonValue


class GraphAlignmentDecisionType(StrEnum):
    SAME_MEANING = "same_meaning"
    ADDS_EVIDENCE = "adds_evidence"
    EXTENDS = "extends"
    REFINES = "refines"
    NARROWS = "narrows"
    BROADENS = "broadens"
    OVERLAPS = "overlaps"
    CONTRADICTS = "contradicts"
    NEW = "new"


@dataclass(frozen=True, slots=True)
class CandidateFact:
    fact_id: FactId
    claim: str
    score: float
    reasons: tuple[str, ...] = ()
    triples_overlap: float = 0.0
    question_overlap: float = 0.0
    entity_overlap: float = 0.0
    metadata: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        if not self.fact_id.strip():
            raise DomainInvariantError("candidate fact_id is required")
        if not self.claim.strip():
            raise DomainInvariantError("candidate fact claim is required")
        _ensure_unit_interval(self.score, "candidate score")
        _ensure_unit_interval(self.triples_overlap, "candidate triples_overlap")
        _ensure_unit_interval(self.question_overlap, "candidate question_overlap")
        _ensure_unit_interval(self.entity_overlap, "candidate entity_overlap")
        for index, reason in enumerate(self.reasons):
            if not reason.strip():
                raise DomainInvariantError(f"candidate reason #{index} is required")


@dataclass(frozen=True, slots=True)
class CandidateFactSet:
    local_claim_ref: str
    candidates: tuple[CandidateFact, ...]
    max_candidates: int = 20

    def __post_init__(self) -> None:
        if not self.local_claim_ref.strip():
            raise DomainInvariantError("candidate fact set local_claim_ref is required")
        if self.max_candidates < 1:
            raise DomainInvariantError("candidate fact set max_candidates must be positive")
        if len(self.candidates) > self.max_candidates:
            raise DomainInvariantError(
                "candidate fact set exceeds max_candidates"
            )
        seen: set[str] = set()
        for candidate in self.candidates:
            if candidate.fact_id in seen:
                raise DomainInvariantError(
                    f"duplicate candidate fact_id: {candidate.fact_id}"
                )
            seen.add(candidate.fact_id)


@dataclass(frozen=True, slots=True)
class GraphAlignmentDecision:
    local_claim_ref: str
    decision_type: GraphAlignmentDecisionType
    confidence: float
    reason: str
    target_fact_id: FactId | None = None
    payload: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        if not self.local_claim_ref.strip():
            raise DomainInvariantError("graph alignment decision local_claim_ref is required")
        _ensure_unit_interval(self.confidence, "graph alignment confidence")
        if not self.reason.strip():
            raise DomainInvariantError("graph alignment decision reason is required")

        if self.decision_type is GraphAlignmentDecisionType.NEW:
            if self.target_fact_id is not None:
                raise DomainInvariantError(
                    "new graph alignment decision must not reference target_fact_id"
                )
            return

        if not self.target_fact_id:
            raise DomainInvariantError(
                f"{self.decision_type.value} graph alignment decision requires target_fact_id"
            )


def _ensure_unit_interval(value: float, label: str) -> None:
    if value < 0 or value > 1:
        raise DomainInvariantError(f"{label} must be in [0, 1]")


__all__ = [
    "CandidateFact",
    "CandidateFactSet",
    "GraphAlignmentDecision",
    "GraphAlignmentDecisionType",
]
