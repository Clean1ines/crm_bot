from __future__ import annotations

from src.domain.project_plane.knowledge_workbench import (
    LocalClaimSearchDocument,
    build_local_claim_candidate_groups,
    build_local_claim_similarity_edges,
)


def _doc(
    *,
    search_document_id: str,
    claim: str,
    triples: tuple[str, ...],
    questions: tuple[str, ...] = (),
    scope: str = "",
    exclusion_scope: str = "",
    evidence: str = "",
    relations: tuple[str, ...] = (),
) -> LocalClaimSearchDocument:
    return LocalClaimSearchDocument(
        search_document_id=search_document_id,
        project_id="project-1",
        document_id="document-1",
        section_id=search_document_id.split(":")[0],
        node_run_id=search_document_id.split(":")[1],
        local_ref=search_document_id.split(":")[2],
        claim=claim,
        claim_kind="capability",
        granularity="atomic",
        triple_texts=triples,
        possible_questions=questions,
        scope=scope,
        exclusion_scope=exclusion_scope,
        evidence_block=evidence or claim,
        relation_texts=relations,
        search_text=claim,
    )


def test_build_local_claim_similarity_edges_detects_semantic_overlap_signals() -> None:
    left = _doc(
        search_document_id="s1:n1:c1",
        claim="Бот автоматически отвечает клиентам в Telegram.",
        triples=("бот has_capability автоматически отвечать клиентам telegram",),
        questions=("Может ли бот отвечать клиентам в Telegram?",),
        scope="автоматические ответы в Telegram",
        exclusion_scope="не ручные ответы менеджера",
        evidence="Бот автоматически отвечает клиентам в Telegram.",
    )
    right = _doc(
        search_document_id="s2:n2:c7",
        claim="Telegram-бот отвечает клиентам автоматически.",
        triples=("telegram бот has_capability отвечать клиентам автоматически",),
        questions=("Отвечает ли бот клиентам автоматически?",),
        scope="автоматические ответы Telegram",
        exclusion_scope="не работа менеджера вручную",
        evidence="Telegram-бот отвечает клиентам автоматически.",
    )

    edges = build_local_claim_similarity_edges((left, right), min_score=0.1)

    assert len(edges) == 1
    edge = edges[0]
    assert edge.source_search_document_id == "s1:n1:c1"
    assert edge.target_search_document_id == "s2:n2:c7"
    assert edge.score > 0.1

    signal_types = {signal.signal_type for signal in edge.signals}
    assert "claim_text_overlap" in signal_types
    assert "question_overlap" in signal_types
    assert "triple_text_overlap" in signal_types
    assert "triple_subject_overlap" in signal_types
    assert "triple_predicate_overlap" in signal_types
    assert "triple_object_overlap" in signal_types
    assert "scope_overlap" in signal_types
    assert "exclusion_scope_overlap" in signal_types
    assert "evidence_overlap" in signal_types


def test_build_local_claim_similarity_edges_ignores_unrelated_claims() -> None:
    left = _doc(
        search_document_id="s1:n1:c1",
        claim="Бот отвечает клиентам.",
        triples=("бот has_capability отвечать клиентам",),
    )
    right = _doc(
        search_document_id="s2:n2:c2",
        claim="Оплата производится банковской картой.",
        triples=("оплата uses банковская карта",),
    )

    edges = build_local_claim_similarity_edges((left, right), min_score=0.18)

    assert edges == ()


def test_build_local_claim_similarity_edges_preserves_deterministic_order() -> None:
    a = _doc(
        search_document_id="s1:n1:c1",
        claim="Бот отвечает клиентам.",
        triples=("бот has_capability отвечать клиентам",),
    )
    b = _doc(
        search_document_id="s2:n2:c2",
        claim="AI бот отвечает клиентам.",
        triples=("бот has_capability отвечать клиентам",),
    )
    c = _doc(
        search_document_id="s3:n3:c3",
        claim="Бот отвечает клиентам в Telegram.",
        triples=("бот has_capability отвечать клиентам telegram",),
    )

    edges = build_local_claim_similarity_edges((a, b, c), min_score=0.1)

    assert tuple(
        (edge.source_search_document_id, edge.target_search_document_id)
        for edge in edges
    ) == tuple(
        sorted(
            (
                (edge.source_search_document_id, edge.target_search_document_id)
                for edge in edges
            ),
            key=lambda pair: (
                -next(
                    edge.score
                    for edge in edges
                    if (
                        edge.source_search_document_id,
                        edge.target_search_document_id,
                    )
                    == pair
                ),
                pair[0],
                pair[1],
            ),
        )
    )


def test_build_local_claim_candidate_groups_builds_connected_components() -> None:
    a = _doc(
        search_document_id="s1:n1:c1",
        claim="Бот отвечает клиентам.",
        triples=("бот has_capability отвечать клиентам",),
    )
    b = _doc(
        search_document_id="s2:n2:c2",
        claim="AI бот отвечает клиентам.",
        triples=("бот has_capability отвечать клиентам",),
    )
    c = _doc(
        search_document_id="s3:n3:c3",
        claim="Оплата производится картой.",
        triples=("оплата uses карта",),
    )

    edges = build_local_claim_similarity_edges((a, b, c), min_score=0.1)
    groups = build_local_claim_candidate_groups((a, b, c), edges)

    assert len(groups) == 2
    assert groups[0].search_document_ids == ("s1:n1:c1", "s2:n2:c2")
    assert groups[0].edge_count == 1
    assert groups[0].max_score > 0
    assert groups[1].search_document_ids == ("s3:n3:c3",)
    assert groups[1].edge_count == 0
    assert groups[1].max_score == 0.0


def test_build_local_claim_similarity_edges_supports_relation_signal() -> None:
    left = _doc(
        search_document_id="s1:n1:c1",
        claim="Бот отвечает клиентам.",
        triples=("бот has_capability отвечать клиентам",),
        relations=("sets_boundary_for -> c2: ручная передача менеджеру ограничивает автоматический ответ",),
    )
    right = _doc(
        search_document_id="s2:n2:c2",
        claim="Сложные вопросы передаются менеджеру.",
        triples=("сложные вопросы requires менеджер",),
        relations=("sets_boundary_for -> c1: ручная передача менеджеру ограничивает автоматический ответ",),
    )

    edges = build_local_claim_similarity_edges((left, right), min_score=0.01)

    assert len(edges) == 1
    assert "local_relation_signal" in {
        signal.signal_type for signal in edges[0].signals
    }
