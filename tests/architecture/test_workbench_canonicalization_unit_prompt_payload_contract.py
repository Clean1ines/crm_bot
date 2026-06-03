from src.domain.project_plane.knowledge_workbench.local_claim_canonicalization import (
    local_claim_canonicalization_units_from_retrieval,
)
from src.domain.project_plane.knowledge_workbench.local_claim_retrieval import (
    LocalClaimSimilarityEdge,
    LocalClaimSimilaritySignal,
    build_local_claim_candidate_groups,
)
from src.domain.project_plane.knowledge_workbench.local_claim_search import (
    LocalClaimSearchDocument,
)


def test_canonicalization_unit_prompt_payload_keeps_full_source_identity_and_evidence() -> None:
    docs = (
        LocalClaimSearchDocument(
            search_document_id="section-1:node-run-1:c1",
            project_id="project-1",
            document_id="document-1",
            section_id="section-1",
            node_run_id="node-run-1",
            local_ref="c1",
            claim="Бот автоматически отвечает клиентам в Telegram.",
            claim_kind="capability",
            granularity="atomic",
            triple_texts=("бот has_capability отвечать клиентам",),
            possible_questions=("Может ли бот отвечать клиентам?",),
            scope="автоматические ответы",
            exclusion_scope="сложные вопросы менеджеру",
            evidence_block="Бот автоматически отвечает клиентам в Telegram.",
            relation_texts=("c1 sets_boundary_for c2: сложные вопросы менеджеру",),
            search_text="claim: Бот автоматически отвечает клиентам в Telegram.",
        ),
        LocalClaimSearchDocument(
            search_document_id="section-2:node-run-2:c7",
            project_id="project-1",
            document_id="document-1",
            section_id="section-2",
            node_run_id="node-run-2",
            local_ref="c7",
            claim="AI-ассистент отвечает покупателям в Telegram.",
            claim_kind="capability",
            granularity="atomic",
            triple_texts=("ассистент has_capability отвечать покупателям",),
            possible_questions=("Отвечает ли ассистент покупателям?",),
            scope="типовые вопросы",
            exclusion_scope="нестандартные обращения",
            evidence_block="AI-ассистент отвечает покупателям в Telegram.",
            relation_texts=(),
            search_text="claim: AI-ассистент отвечает покупателям в Telegram.",
        ),
    )

    edges = (
        LocalClaimSimilarityEdge(
            source_search_document_id="section-1:node-run-1:c1",
            target_search_document_id="section-2:node-run-2:c7",
            score=0.71,
            signals=(
                LocalClaimSimilaritySignal(
                    signal_type="triple_predicate_overlap",
                    score=1.0,
                    matched_values=("has_capability",),
                ),
            ),
        ),
    )

    groups = build_local_claim_candidate_groups(docs, edges)
    units = local_claim_canonicalization_units_from_retrieval(
        search_documents=docs,
        candidate_groups=groups,
        similarity_edges=edges,
    )

    payload = units[0].to_prompt_payload()
    member = payload["members"][0]
    edge = payload["similarity_edges"][0]
    signal = edge["signals"][0]

    assert member["project_id"] == "project-1"
    assert member["document_id"] == "document-1"
    assert member["section_id"] == "section-1"
    assert member["node_run_id"] == "node-run-1"
    assert member["local_ref"] == "c1"
    assert member["claim"]
    assert member["triples"] == ["бот has_capability отвечать клиентам"]
    assert member["possible_questions"] == ["Может ли бот отвечать клиентам?"]
    assert member["scope"] == "автоматические ответы"
    assert member["exclusion_scope"] == "сложные вопросы менеджеру"
    assert member["evidence_block"]
    assert member["local_relations"]

    assert edge["source_search_document_id"] == "section-1:node-run-1:c1"
    assert edge["target_search_document_id"] == "section-2:node-run-2:c7"
    assert edge["score"] == 0.71
    assert signal["signal_type"] == "triple_predicate_overlap"
    assert signal["score"] == 1.0
    assert signal["matched_values"] == ["has_capability"]
