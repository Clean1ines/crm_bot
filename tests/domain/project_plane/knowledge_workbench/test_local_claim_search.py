from __future__ import annotations

from src.domain.project_plane.knowledge_workbench import (
    LocalClaim,
    LocalClaimGraph,
    LocalClaimRelation,
    LocalClaimTriple,
    LocalEvidenceMention,
    LocalClaimSearchDocument,
    local_claim_search_document_from_claim,
    local_claim_search_documents_from_graph,
    local_claim_search_documents_from_graphs,
)


def _claim(
    *,
    local_ref: str = "c1",
    claim: str = "Бот автоматически отвечает клиентам в Telegram.",
) -> LocalClaim:
    return LocalClaim(
        local_ref=local_ref,
        claim=claim,
        claim_kind="capability",
        granularity="atomic",
        triples=(
            LocalClaimTriple(
                subject="бот",
                predicate="has_capability",
                object="автоматически отвечать клиентам в Telegram",
            ),
        ),
        evidence=LocalEvidenceMention(
            evidence_block="Бот автоматически отвечает клиентам в Telegram.",
            source_refs=("source-ref-1",),
            source_chunk_indexes=(0,),
        ),
        possible_questions=(
            "Может ли бот отвечать клиентам в Telegram?",
            "Где бот отвечает клиентам?",
        ),
        scope="автоматические ответы в Telegram",
        exclusion_scope="не ручные ответы менеджера",
        local_relations=(
            LocalClaimRelation(
                target_ref="c2",
                relation="sets_boundary_for",
                reason="ручная передача менеджеру ограничивает автоматический ответ",
            ),
        ),
        confidence=0.92,
    )


def _graph(*claims: LocalClaim) -> LocalClaimGraph:
    return LocalClaimGraph(
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        node_run_id="node-run-1",
        claims=claims or (_claim(),),
    )


def test_local_claim_search_document_from_claim_preserves_identity_fields() -> None:
    graph = _graph()
    document = local_claim_search_document_from_claim(
        graph=graph,
        claim=graph.claims[0],
    )

    assert isinstance(document, LocalClaimSearchDocument)
    assert document.search_document_id == "section-1:node-run-1:c1"
    assert document.project_id == "project-1"
    assert document.document_id == "document-1"
    assert document.section_id == "section-1"
    assert document.node_run_id == "node-run-1"
    assert document.local_ref == "c1"
    assert document.claim == "Бот автоматически отвечает клиентам в Telegram."
    assert document.claim_kind == "capability"
    assert document.granularity == "atomic"


def test_local_claim_search_text_includes_full_semantic_object() -> None:
    graph = _graph()
    document = local_claim_search_document_from_claim(
        graph=graph,
        claim=graph.claims[0],
    )

    assert (
        "claim: Бот автоматически отвечает клиентам в Telegram." in document.search_text
    )
    assert "claim_kind: capability" in document.search_text
    assert "granularity: atomic" in document.search_text

    assert "triples:" in document.search_text
    assert "бот has_capability автоматически отвечать клиентам в Telegram" in (
        document.search_text
    )

    assert "possible_questions:" in document.search_text
    assert "Может ли бот отвечать клиентам в Telegram?" in document.search_text
    assert "Где бот отвечает клиентам?" in document.search_text

    assert "scope: автоматические ответы в Telegram" in document.search_text
    assert "exclusion_scope: не ручные ответы менеджера" in document.search_text
    assert "evidence: Бот автоматически отвечает клиентам в Telegram." in (
        document.search_text
    )

    assert "local_relations:" in document.search_text
    assert (
        "sets_boundary_for -> c2: ручная передача менеджеру ограничивает автоматический ответ"
        in document.search_text
    )


def test_local_claim_search_document_exposes_structured_search_parts() -> None:
    graph = _graph()
    document = local_claim_search_document_from_claim(
        graph=graph,
        claim=graph.claims[0],
    )

    assert document.triple_texts == (
        "бот has_capability автоматически отвечать клиентам в Telegram",
    )
    assert document.possible_questions == (
        "Может ли бот отвечать клиентам в Telegram?",
        "Где бот отвечает клиентам?",
    )
    assert document.scope == "автоматические ответы в Telegram"
    assert document.exclusion_scope == "не ручные ответы менеджера"
    assert document.evidence_block == "Бот автоматически отвечает клиентам в Telegram."
    assert document.relation_texts == (
        "sets_boundary_for -> c2: ручная передача менеджеру ограничивает автоматический ответ",
    )


def test_local_claim_search_documents_from_graph_preserves_claim_order() -> None:
    graph = _graph(
        _claim(local_ref="c1", claim="Первый claim."),
        _claim(local_ref="c2", claim="Второй claim."),
    )

    documents = local_claim_search_documents_from_graph(graph)

    assert tuple(document.local_ref for document in documents) == ("c1", "c2")
    assert tuple(document.claim for document in documents) == (
        "Первый claim.",
        "Второй claim.",
    )


def test_local_claim_search_documents_from_graphs_preserves_graph_order() -> None:
    graph_1 = _graph(_claim(local_ref="c1", claim="Первый claim."))
    graph_2 = LocalClaimGraph(
        project_id="project-1",
        document_id="document-1",
        section_id="section-2",
        node_run_id="node-run-2",
        claims=(_claim(local_ref="c2", claim="Второй claim."),),
    )

    documents = local_claim_search_documents_from_graphs((graph_1, graph_2))

    assert tuple(document.search_document_id for document in documents) == (
        "section-1:node-run-1:c1",
        "section-2:node-run-2:c2",
    )
