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


def _unit_vector_with_raw_cosine(raw_cosine: float) -> tuple[float, float]:
    import math

    return (raw_cosine, math.sqrt(1.0 - raw_cosine * raw_cosine))


def test_strong_vector_axole_claims_are_compaction_candidates() -> None:
    edges = DraftClaimHybridSimilarityPolicy(threshold=0.78).build_edges(
        (
            _claim(
                "claim-a",
                "Axole — это система для запуска AI-поддержки в Telegram на основе документов бизнеса.",
                (1.0, 0.0),
                question="Что такое Axole?",
                granularity="atomic",
                exclusion_scope=("Telegram", "AI-поддержка", "база знаний"),
            ),
            _claim(
                "claim-b",
                "Axole позволяет бизнесу запустить AI-поддержку в Telegram по своим документам без ручного написания FAQ-сценариев.",
                _unit_vector_with_raw_cosine(0.82),
                question="Как Axole помогает бизнесу?",
                granularity="composite",
                exclusion_scope=("Telegram-ассистент", "FAQ-сценарии"),
            ),
        )
    )

    assert len(edges) == 1
    assert edges[0].vector_score >= 0.87
    assert edges[0].combined_score >= 0.78
    assert edges[0].signals["edge_kind"] == "strong_vector_candidate"


def test_medium_vector_claims_need_surface_support() -> None:
    edges = DraftClaimHybridSimilarityPolicy(threshold=0.78).build_edges(
        (
            _claim(
                "claim-a",
                "Курация знаний помогает проверить черновые знания перед публикацией.",
                (1.0, 0.0),
                question="Что такое курация знаний?",
                granularity="composite",
            ),
            _claim(
                "claim-b",
                "Черновые знания требуют группировки и курации перед публикацией.",
                _unit_vector_with_raw_cosine(0.70),
                question="Зачем нужна курация знаний?",
                granularity="composite",
            ),
        )
    )

    assert len(edges) == 1
    assert 0.85 <= edges[0].vector_score < 0.87
    assert edges[0].signals["edge_kind"] == "supported_vector_candidate"


def test_weak_vector_claims_need_strong_surface_support() -> None:
    edges = DraftClaimHybridSimilarityPolicy(threshold=0.78).build_edges(
        (
            _claim(
                "claim-a",
                "Axole не является полноценной CRM, но содержит CRM-like слой.",
                (1.0, 0.0),
                question="Является ли Axole CRM?",
                granularity="atomic",
                exclusion_scope=("CRM", "AmoCRM", "HubSpot"),
            ),
            _claim(
                "claim-b",
                "Axole не заменяет AmoCRM или HubSpot, но предоставляет CRM-like слой для AI-поддержки.",
                _unit_vector_with_raw_cosine(0.64),
                question="Какие CRM-функции доступны в Axole?",
                granularity="composite",
                exclusion_scope=("CRM", "AmoCRM", "HubSpot"),
            ),
        )
    )

    assert len(edges) == 1
    assert 0.82 <= edges[0].vector_score < 0.85
    assert edges[0].signals["edge_kind"] == "surface_supported_candidate"


def test_weak_vector_without_surface_support_is_not_edge() -> None:
    edges = DraftClaimHybridSimilarityPolicy(threshold=0.78).build_edges(
        (
            _claim(
                "claim-a",
                "Axole нужен для управляемой базы знаний.",
                (1.0, 0.0),
                question="Зачем нужен Axole?",
                granularity="composite",
                exclusion_scope=("база знаний",),
            ),
            _claim(
                "claim-b",
                "Стоимость зависит от объёма базы, документов и требований.",
                _unit_vector_with_raw_cosine(0.64),
                question="Сколько стоит продукт?",
                granularity="composite",
                exclusion_scope=("стоимость",),
            ),
        )
    )

    assert edges == ()
