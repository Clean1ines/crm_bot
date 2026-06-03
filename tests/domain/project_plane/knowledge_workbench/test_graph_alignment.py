from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_workbench import (
    CandidateFact,
    CandidateFactSet,
    DomainInvariantError,
    GraphAlignmentDecision,
    GraphAlignmentDecisionType,
)


def _candidate(fact_id: str = "fact-1") -> CandidateFact:
    return CandidateFact(
        fact_id=fact_id,
        claim="Продукт проверяет знания.",
        score=0.82,
        reasons=("same subject",),
        triples_overlap=0.7,
        question_overlap=0.5,
        entity_overlap=0.4,
    )


def test_candidate_fact_set_allows_bounded_candidates() -> None:
    candidates = tuple(_candidate(f"fact-{index}") for index in range(1, 21))

    candidate_set = CandidateFactSet(
        local_claim_ref="c1",
        candidates=candidates,
    )

    assert candidate_set.local_claim_ref == "c1"
    assert len(candidate_set.candidates) == 20


def test_candidate_fact_set_rejects_more_than_twenty_candidates() -> None:
    candidates = tuple(_candidate(f"fact-{index}") for index in range(1, 22))

    with pytest.raises(DomainInvariantError, match="exceeds max_candidates"):
        CandidateFactSet(
            local_claim_ref="c1",
            candidates=candidates,
        )


def test_candidate_fact_set_rejects_duplicate_fact_ids() -> None:
    with pytest.raises(DomainInvariantError, match="duplicate candidate fact_id"):
        CandidateFactSet(
            local_claim_ref="c1",
            candidates=(_candidate("fact-1"), _candidate("fact-1")),
        )


def test_non_new_graph_alignment_decision_requires_target_fact_id() -> None:
    with pytest.raises(DomainInvariantError, match="requires target_fact_id"):
        GraphAlignmentDecision(
            local_claim_ref="c1",
            decision_type=GraphAlignmentDecisionType.SAME_MEANING,
            confidence=0.9,
            reason="same triples",
            target_fact_id=None,
        )


def test_new_graph_alignment_decision_must_not_reference_target_fact_id() -> None:
    with pytest.raises(DomainInvariantError, match="must not reference target_fact_id"):
        GraphAlignmentDecision(
            local_claim_ref="c1",
            decision_type=GraphAlignmentDecisionType.NEW,
            confidence=0.9,
            reason="no candidates match",
            target_fact_id="fact-1",
        )


def test_graph_alignment_decision_accepts_all_targeted_relation_types() -> None:
    targeted = (
        GraphAlignmentDecisionType.SAME_MEANING,
        GraphAlignmentDecisionType.ADDS_EVIDENCE,
        GraphAlignmentDecisionType.EXTENDS,
        GraphAlignmentDecisionType.REFINES,
        GraphAlignmentDecisionType.NARROWS,
        GraphAlignmentDecisionType.BROADENS,
        GraphAlignmentDecisionType.OVERLAPS,
        GraphAlignmentDecisionType.CONTRADICTS,
    )

    for decision_type in targeted:
        decision = GraphAlignmentDecision(
            local_claim_ref="c1",
            decision_type=decision_type,
            confidence=0.8,
            reason="candidate comparison",
            target_fact_id="fact-1",
        )

        assert decision.target_fact_id == "fact-1"


def test_new_graph_alignment_decision_without_candidates_is_valid() -> None:
    decision = GraphAlignmentDecision(
        local_claim_ref="c1",
        decision_type=GraphAlignmentDecisionType.NEW,
        confidence=0.75,
        reason="candidate set is empty",
    )

    assert decision.target_fact_id is None
