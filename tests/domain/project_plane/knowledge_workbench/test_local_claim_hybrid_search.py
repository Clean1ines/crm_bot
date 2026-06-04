from __future__ import annotations

from src.domain.project_plane.knowledge_workbench.local_claim_canonicalization import (
    local_claim_canonicalization_units_from_retrieval,
)
from src.domain.project_plane.knowledge_workbench.local_claim_retrieval import (
    build_local_claim_candidate_groups,
    build_local_claim_hybrid_similarity_edges,
    build_local_claim_hybrid_similarity_edges_with_trace,
)
from src.domain.project_plane.knowledge_workbench.local_claim_search import (
    LocalClaimSearchDocument,
)


def _doc(
    search_document_id: str,
    claim: str,
    *,
    triple_texts: tuple[str, ...],
    questions: tuple[str, ...],
    scope: str,
    evidence: str,
) -> LocalClaimSearchDocument:
    search_text = "\n".join(
        (
            f"claim: {claim}",
            "triples:",
            *triple_texts,
            "possible_questions:",
            *questions,
            f"scope: {scope}",
            f"evidence: {evidence}",
        )
    )
    return LocalClaimSearchDocument(
        search_document_id=search_document_id,
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        node_run_id="node-run-1",
        local_ref=search_document_id,
        claim=claim,
        claim_kind="policy",
        granularity="atomic",
        triple_texts=triple_texts,
        possible_questions=questions,
        scope=scope,
        exclusion_scope="",
        evidence_block=evidence,
        relation_texts=(),
        search_text=search_text,
    )


def test_hybrid_search_forms_clusters_from_lexical_questions_triples_and_ngrams() -> (
    None
):
    refund_a = _doc(
        "claim-a",
        "Клиент может вернуть товар в течение 14 дней после покупки.",
        triple_texts=("клиент can_return товар", "возврат has_window 14 дней"),
        questions=("как вернуть товар", "какой срок возврата"),
        scope="правила возврата товара",
        evidence="Возврат товара возможен в течение 14 дней.",
    )
    refund_b = _doc(
        "claim-b",
        "Покупатель оформляет возврат товара не позднее четырнадцати дней.",
        triple_texts=(
            "покупатель can_return товар",
            "возврат has_window четырнадцать дней",
        ),
        questions=("можно ли вернуть товар", "сколько дней на возврат"),
        scope="сроки возврата товара",
        evidence="Покупатель может оформить возврат в течение четырнадцати дней.",
    )
    delivery = _doc(
        "claim-c",
        "Доставка выполняется курьером после подтверждения заказа.",
        triple_texts=(
            "курьер delivers заказ",
            "заказ requires_confirmation подтверждение",
        ),
        questions=("как работает доставка", "когда приезжает курьер"),
        scope="доставка заказа",
        evidence="Курьер доставляет подтвержденный заказ.",
    )

    documents = (refund_a, refund_b, delivery)

    edges, trace = build_local_claim_hybrid_similarity_edges_with_trace(
        documents,
        min_score=0.08,
        candidate_limit_per_document=20,
    )

    assert trace.document_count == 3
    assert trace.token_posting_count > 0
    assert trace.ngram_posting_count > 0
    assert trace.candidate_pair_count > 0
    assert trace.emitted_edge_count == len(edges)

    assert any(
        {edge.source_search_document_id, edge.target_search_document_id}
        == {"claim-a", "claim-b"}
        for edge in edges
    )
    assert not any(
        {edge.source_search_document_id, edge.target_search_document_id}
        == {"claim-a", "claim-c"}
        for edge in edges
        if edge.score >= 0.22
    )

    groups = build_local_claim_candidate_groups(documents, edges)
    grouped_ids = {group.search_document_ids for group in groups}

    assert ("claim-a", "claim-b") in grouped_ids
    assert ("claim-c",) in grouped_ids

    units = local_claim_canonicalization_units_from_retrieval(
        search_documents=documents,
        candidate_groups=groups,
        similarity_edges=edges,
    )

    refund_unit = next(
        unit
        for unit in units
        if tuple(member.search_document_id for member in unit.members)
        == ("claim-a", "claim-b")
    )
    assert refund_unit.member_count == 2
    assert refund_unit.edge_count >= 1
    assert refund_unit.to_prompt_payload()["members"][0]["search_text"]


def test_hybrid_similarity_edges_are_available_as_default_business_entrypoint() -> None:
    left = _doc(
        "left",
        "FAQ бот отвечает на вопросы клиентов из базы знаний.",
        triple_texts=("бот answers вопрос", "ответ uses база_знаний"),
        questions=("как бот отвечает",),
        scope="ответы FAQ",
        evidence="Бот использует базу знаний.",
    )
    right = _doc(
        "right",
        "Ассистент отвечает клиентам на FAQ вопросы по знаниям проекта.",
        triple_texts=("ассистент answers вопрос", "ответ uses знания"),
        questions=("как ассистент отвечает",),
        scope="ответы FAQ",
        evidence="Ассистент использует знания проекта.",
    )

    edges = build_local_claim_hybrid_similarity_edges(
        (left, right),
        min_score=0.05,
    )

    assert len(edges) == 1
    assert edges[0].score > 0.05
    assert {signal.signal_type for signal in edges[0].signals} >= {
        "search_text_token_overlap",
        "search_text_char_ngram_overlap",
    }
