from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_grouping_policy import (
    DraftClaimCompactionGroupingPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_hybrid_similarity_policy import (
    DraftClaimHybridSimilarityPolicy,
)


def _claim(ref: str, vector: tuple[float, ...] = (1.0, 0.0)) -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=ref,
        embedding_ref=f"embedding:{ref}",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        source_unit_ref=f"unit:{ref}",
        claim="Product supports refunds",
        possible_questions=("Does product support refunds?",),
        exclusion_scope=(),
        granularity="atomic",
        embedding_text="Product supports refunds",
        embedding_model_id="openai/gpt-oss-120b",
        dimensions=len(vector),
        vector=vector,
    )


def test_connected_edges_become_one_group_and_singletons_are_preserved() -> None:
    claims = (
        _claim("claim-a"),
        _claim("claim-b"),
        _claim("claim-c", (0.0, 1.0)),
    )
    edge = DraftClaimHybridSimilarityPolicy(threshold=0.0).build_edges(claims[:2])[0]

    groups = DraftClaimCompactionGroupingPolicy(group_threshold=0.78).build_groups(
        claims,
        (edge,),
    )

    members = {group.member_observation_refs for group in groups}
    assert ("claim-a", "claim-b") in members
    assert ("claim-c",) in members


def test_group_ref_is_deterministic_independent_of_edge_order() -> None:
    claims = (_claim("claim-a"), _claim("claim-b"), _claim("claim-c"))
    edges = DraftClaimHybridSimilarityPolicy(threshold=0.0).build_edges(claims)

    forward = DraftClaimCompactionGroupingPolicy(group_threshold=0.0).build_groups(
        claims,
        edges,
    )
    reverse = DraftClaimCompactionGroupingPolicy(group_threshold=0.0).build_groups(
        claims,
        tuple(reversed(edges)),
    )

    assert tuple(group.group_ref for group in forward) == tuple(
        group.group_ref for group in reverse
    )
