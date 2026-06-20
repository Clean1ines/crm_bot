from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionEdgeCandidate,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_grouping_policy import (
    DraftClaimCompactionGroupingPolicy,
)


def _claim(ref: str) -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=ref,
        embedding_ref=f"embedding:{ref}",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        source_unit_ref=f"unit:{ref}",
        claim=f"Claim {ref}",
        possible_questions=(f"Question {ref}?",),
        exclusion_scope=(),
        granularity="atomic",
        embedding_text=f"Claim {ref}",
        embedding_model_id="sentence-transformers/all-MiniLM-L6-v2",
        dimensions=2,
        vector=(1.0, 0.0),
    )


def _edge(
    left: str, right: str, score: float = 0.95
) -> DraftClaimCompactionEdgeCandidate:
    ordered_left, ordered_right = sorted((left, right))
    return DraftClaimCompactionEdgeCandidate(
        edge_ref=f"edge:{ordered_left}:{ordered_right}",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        left_observation_ref=ordered_left,
        right_observation_ref=ordered_right,
        left_embedding_ref=f"embedding:{ordered_left}",
        right_embedding_ref=f"embedding:{ordered_right}",
        vector_score=score,
        lexical_score=0.2,
        question_overlap_score=0.2,
        exclusion_scope_score=0.0,
        granularity_score=1.0,
        combined_score=score,
        signals={"edge_kind": "vector_candidate"},
    )


def test_grouping_builds_connected_components_from_candidate_edges() -> None:
    claims = tuple(_claim(ref) for ref in ("a", "b", "c", "d"))
    groups = DraftClaimCompactionGroupingPolicy().build_groups(
        claims,
        (
            _edge("a", "b"),
            _edge("b", "c"),
        ),
    )

    member_sets = {group.member_observation_refs for group in groups}

    assert ("a", "b", "c") in member_sets
    assert ("d",) in member_sets


def test_grouping_does_not_limit_large_cluster_size() -> None:
    refs = tuple(f"claim-{index:02d}" for index in range(30))
    claims = tuple(_claim(ref) for ref in refs)
    groups = DraftClaimCompactionGroupingPolicy().build_groups(
        claims,
        tuple(_edge(left, right) for left, right in zip(refs, refs[1:], strict=False)),
    )

    assert len(groups) == 1
    assert groups[0].member_observation_refs == refs
    assert groups[0].requires_split is False
