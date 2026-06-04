from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    LocalClaimSearchDocument,
    build_local_claim_candidate_groups,
    build_local_claim_similarity_edges,
    local_claim_canonicalization_units_from_retrieval,
)


def _doc(
    *,
    search_document_id: str,
    claim: str,
    triple_texts: tuple[str, ...],
    possible_questions: tuple[str, ...] = (),
    scope: str = "",
    exclusion_scope: str = "",
    evidence_block: str = "",
) -> LocalClaimSearchDocument:
    section_id, node_run_id, local_ref = search_document_id.split(":")
    return LocalClaimSearchDocument(
        search_document_id=search_document_id,
        project_id="project-1",
        document_id="document-1",
        section_id=section_id,
        node_run_id=node_run_id,
        local_ref=local_ref,
        claim=claim,
        claim_kind="capability",
        granularity="atomic",
        triple_texts=triple_texts,
        possible_questions=possible_questions,
        scope=scope,
        exclusion_scope=exclusion_scope,
        evidence_block=evidence_block or claim,
        relation_texts=(),
        search_text=claim,
    )


def test_canonicalization_units_preserve_candidate_group_members_and_edges() -> None:
    first = _doc(
        search_document_id="section-1:node-run-1:c1",
        claim="Бот автоматически отвечает клиентам в Telegram.",
        triple_texts=("бот has_capability автоматически отвечать клиентам telegram",),
        possible_questions=("Может ли бот отвечать клиентам?",),
        scope="автоматические ответы telegram",
        exclusion_scope="не ручные ответы менеджера",
    )
    second = _doc(
        search_document_id="section-2:node-run-2:c2",
        claim="Telegram-бот отвечает клиентам автоматически.",
        triple_texts=("telegram бот has_capability отвечать клиентам автоматически",),
        possible_questions=("Отвечает ли бот клиентам автоматически?",),
        scope="автоматические ответы telegram",
        exclusion_scope="не работа менеджера вручную",
    )
    unrelated = _doc(
        search_document_id="section-3:node-run-3:c3",
        claim="Оплата производится банковской картой.",
        triple_texts=("оплата uses банковская карта",),
        possible_questions=("Как оплатить заказ?",),
        scope="оплата заказа",
    )

    documents = (first, second, unrelated)
    edges = build_local_claim_similarity_edges(documents, min_score=0.1)
    groups = build_local_claim_candidate_groups(documents, edges)

    units = local_claim_canonicalization_units_from_retrieval(
        search_documents=documents,
        candidate_groups=groups,
        similarity_edges=edges,
    )

    assert len(units) == 2

    first_unit = units[0]
    assert first_unit.unit_id == "canonicalization-unit-1"
    assert first_unit.member_count == 2
    assert first_unit.edge_count == 1
    assert first_unit.max_similarity_score > 0
    assert tuple(member.local_ref for member in first_unit.members) == ("c1", "c2")
    assert first_unit.edges[0].source_search_document_id == ("section-1:node-run-1:c1")
    assert first_unit.edges[0].target_search_document_id == ("section-2:node-run-2:c2")
    assert first_unit.edges[0].signal_summaries

    second_unit = units[1]
    assert second_unit.member_count == 1
    assert second_unit.edge_count == 0
    assert second_unit.members[0].local_ref == "c3"


def test_canonicalization_unit_prompt_payload_is_prompt_c_ready_without_registry_merge_vocabulary() -> (
    None
):
    first = _doc(
        search_document_id="section-1:node-run-1:c1",
        claim="Бот автоматически отвечает клиентам в Telegram.",
        triple_texts=("бот has_capability автоматически отвечать клиентам telegram",),
        possible_questions=("Может ли бот отвечать клиентам?",),
        scope="автоматические ответы telegram",
        exclusion_scope="не ручные ответы менеджера",
    )
    second = _doc(
        search_document_id="section-2:node-run-2:c2",
        claim="Telegram-бот отвечает клиентам автоматически.",
        triple_texts=("telegram бот has_capability отвечать клиентам автоматически",),
        possible_questions=("Отвечает ли бот клиентам автоматически?",),
        scope="автоматические ответы telegram",
        exclusion_scope="не работа менеджера вручную",
    )

    documents = (first, second)
    edges = build_local_claim_similarity_edges(documents, min_score=0.1)
    groups = build_local_claim_candidate_groups(documents, edges)
    unit = local_claim_canonicalization_units_from_retrieval(
        search_documents=documents,
        candidate_groups=groups,
        similarity_edges=edges,
    )[0]

    payload = unit.to_prompt_payload()

    assert payload["unit_id"] == "canonicalization-unit-1"
    assert payload["group_id"] == unit.group_id
    assert len(payload["members"]) == 2
    assert len(payload["similarity_edges"]) == 1

    first_member = payload["members"][0]
    assert first_member["local_ref"] == "c1"
    assert first_member["claim"] == "Бот автоматически отвечает клиентам в Telegram."
    assert first_member["triples"] == [
        "бот has_capability автоматически отвечать клиентам telegram"
    ]
    assert first_member["possible_questions"] == ["Может ли бот отвечать клиентам?"]
    assert first_member["scope"] == "автоматические ответы telegram"
    assert first_member["exclusion_scope"] == "не ручные ответы менеджера"

    assert "claim_inputs" not in payload
    assert "candidate_fact_sets" not in payload
    assert "section" not in payload


def test_canonicalization_units_reject_unknown_group_member() -> None:
    document = _doc(
        search_document_id="section-1:node-run-1:c1",
        claim="Бот отвечает клиентам.",
        triple_texts=("бот has_capability отвечать клиентам",),
    )
    edges = build_local_claim_similarity_edges((document,), min_score=0.1)
    groups = build_local_claim_candidate_groups((document,), edges)
    broken_group = type(groups[0])(
        group_id=groups[0].group_id,
        search_document_ids=("missing:node:c404",),
        edge_count=0,
        max_score=0.0,
    )

    with pytest.raises(DomainInvariantError, match="unknown search document"):
        local_claim_canonicalization_units_from_retrieval(
            search_documents=(document,),
            candidate_groups=(broken_group,),
            similarity_edges=(),
        )
