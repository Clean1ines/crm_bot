from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_hybrid_similarity_policy import (
    DraftClaimHybridSimilarityPolicy,
)


def _claim(
    ref: str,
    claim: str,
    vector: tuple[float, ...],
    *,
    question: str = "What is refund policy?",
    granularity: str = "atomic",
    exclusion_scope: tuple[str, ...] = (),
) -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=ref,
        embedding_ref=f"embedding:{ref}",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        source_unit_ref=f"unit:{ref}",
        claim=claim,
        possible_questions=(question,),
        exclusion_scope=exclusion_scope,
        granularity=granularity,
        embedding_text=claim,
        embedding_model_id="openai/gpt-oss-120b",
        dimensions=len(vector),
        vector=vector,
    )


def test_identical_vectors_and_overlapping_questions_get_high_score() -> None:
    edges = DraftClaimHybridSimilarityPolicy(threshold=0.78).build_edges(
        (
            _claim("claim-a", "Product supports refunds", (1.0, 0.0)),
            _claim("claim-b", "Product supports refunds", (1.0, 0.0)),
        )
    )

    assert len(edges) == 1
    assert edges[0].combined_score >= 0.78
    assert edges[0].signals["vector_score"] == 1.0
    assert "question_overlap_score" in edges[0].signals
    assert "lexical_score" in edges[0].signals
    assert "granularity_score" in edges[0].signals
    assert "exclusion_scope_score" in edges[0].signals


def test_unrelated_vectors_and_text_get_below_threshold() -> None:
    edges = DraftClaimHybridSimilarityPolicy(threshold=0.78).build_edges(
        (
            _claim("claim-a", "Refund policy", (1.0, 0.0), question="Refunds?"),
            _claim("claim-b", "Warehouse schedule", (0.0, 1.0), question="Delivery?"),
        )
    )

    assert edges == ()


def test_pair_ref_is_deterministic_independent_of_input_order() -> None:
    policy = DraftClaimHybridSimilarityPolicy(threshold=0.0)
    left = _claim("claim-a", "Refund policy", (1.0, 0.0))
    right = _claim("claim-b", "Refund policy", (1.0, 0.0))

    forward = policy.build_edges((left, right))
    reverse = policy.build_edges((right, left))

    assert forward[0].edge_ref == reverse[0].edge_ref
    assert forward[0].left_observation_ref == "claim-a"
    assert forward[0].right_observation_ref == "claim-b"
