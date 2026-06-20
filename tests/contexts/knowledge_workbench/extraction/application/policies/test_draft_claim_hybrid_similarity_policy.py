from __future__ import annotations

import math

import pytest

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
        embedding_model_id="sentence-transformers/all-MiniLM-L6-v2",
        dimensions=len(vector),
        vector=vector,
    )


def _unit_vector_with_raw_cosine(raw_cosine: float) -> tuple[float, float]:
    return (raw_cosine, math.sqrt(1.0 - raw_cosine * raw_cosine))


def test_raw_085_is_candidate_edge_for_llm_compaction() -> None:
    edges = DraftClaimHybridSimilarityPolicy().build_edges(
        (
            _claim(
                "claim-a",
                "Axole запускает AI-поддержку в Telegram на основе документов бизнеса.",
                (1.0, 0.0),
                question="Что такое Axole?",
            ),
            _claim(
                "claim-b",
                "Axole помогает бизнесу запустить Telegram AI-поддержку по своим документам.",
                _unit_vector_with_raw_cosine(0.85),
                question="Как Axole помогает бизнесу?",
            ),
        )
    )

    assert len(edges) == 1
    assert edges[0].signals["policy_version"] == "simple_candidate_clustering_v1"
    assert edges[0].signals["score_space"] == "affine_normalized_cosine_v1"
    assert edges[0].signals["raw_cosine_score"] == pytest.approx(0.85)
    assert edges[0].signals["admitted_by_policy"] is True
    assert edges[0].signals["edge_kind"] == "vector_candidate"


def test_raw_082_with_surface_support_is_candidate_edge() -> None:
    edges = DraftClaimHybridSimilarityPolicy().build_edges(
        (
            _claim(
                "claim-a",
                "Курация знаний помогает проверить черновые знания перед публикацией.",
                (1.0, 0.0),
                question="Зачем нужна курация знаний?",
                granularity="composite",
            ),
            _claim(
                "claim-b",
                "Черновые знания требуют группировки и курации перед публикацией.",
                _unit_vector_with_raw_cosine(0.82),
                question="Для чего нужна курация знаний?",
                granularity="composite",
            ),
        )
    )

    assert len(edges) == 1
    assert edges[0].signals["raw_cosine_score"] == pytest.approx(0.82)
    assert edges[0].signals["edge_kind"] == "surface_supported_vector_candidate"


def test_raw_080_with_strong_surface_support_is_review_candidate_edge() -> None:
    edges = DraftClaimHybridSimilarityPolicy().build_edges(
        (
            _claim(
                "claim-a",
                "В Axole есть веб-панель для команды бизнеса.",
                (1.0, 0.0),
                question="Есть ли веб-панель?",
                exclusion_scope=("веб-панель", "web-widget", "команда бизнеса"),
            ),
            _claim(
                "claim-b",
                "Клиентский web-widget для сайта пока не является готовой функцией.",
                _unit_vector_with_raw_cosine(0.80),
                question="Есть ли web-widget для сайта?",
                exclusion_scope=("web-widget", "сайт", "будущее"),
            ),
        )
    )

    assert len(edges) == 1
    assert edges[0].signals["raw_cosine_score"] == pytest.approx(0.80)
    assert edges[0].signals["edge_kind"] == "review_candidate"


def test_unrelated_vectors_and_text_are_not_candidate_edges() -> None:
    edges = DraftClaimHybridSimilarityPolicy().build_edges(
        (
            _claim("claim-a", "Refund policy", (1.0, 0.0), question="Refunds?"),
            _claim("claim-b", "Warehouse schedule", (0.0, 1.0), question="Delivery?"),
        )
    )

    assert edges == ()


def test_admitted_edge_keeps_diagnostic_score_instead_of_threshold_floor() -> None:
    policy = DraftClaimHybridSimilarityPolicy(threshold=0.99)
    edge = policy._build_edge(
        _claim("claim-a", "Alpha", (1.0, 0.0), question="Alpha?"),
        _claim(
            "claim-b",
            "Beta",
            _unit_vector_with_raw_cosine(0.85),
            question="Beta?",
        ),
    )

    assert edge.signals["admitted_by_policy"] is True
    assert edge.combined_score == edge.vector_score
    assert edge.combined_score < policy.threshold
