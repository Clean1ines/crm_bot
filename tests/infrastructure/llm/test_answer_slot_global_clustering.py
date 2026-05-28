from __future__ import annotations

from typing import cast

from src.domain.project_plane.retrieval_surface_compilation import (
    LocalSurfaceRelation,
    SurfaceAnswerDraft,
    SurfaceRelationType,
)
from src.infrastructure.llm.knowledge_surface_full_graph_compiler import (
    _answer_slot_clusters,
)


def _draft(
    key: str,
    *,
    title: str,
    question: str,
    answer: str,
    source_refs: tuple[str, ...] = (),
) -> SurfaceAnswerDraft:
    return SurfaceAnswerDraft(
        id=f"draft-{key}",
        run_id="run-1",
        document_id="doc-1",
        candidate_key=key,
        title=title,
        canonical_question=question,
        short_answer=answer[:80],
        answer=answer,
        answer_scope=answer,
        question_scope=question,
        exclusion_scope="",
        source_refs=source_refs,
        warnings=(),
    )


def _relation(
    source: str,
    target: str,
    relation_type: str,
    *,
    confidence: float = 0.9,
) -> LocalSurfaceRelation:
    return LocalSurfaceRelation(
        id=f"rel-{source}-{target}",
        run_id="run-1",
        document_id="doc-1",
        source_unit_id="unit-1",
        source_surface_key=source,
        target_surface_key=target,
        relation_type=cast(SurfaceRelationType, relation_type),
        confidence=confidence,
        reason="test relation",
    )


def test_answer_slot_clusters_group_summary_with_richer_same_intent_answer() -> None:
    short = _draft(
        "short_product",
        title="Product overview",
        question="What is this service?",
        answer="Knowledge-base platform, curation, retrieval quality, assistant.",
        source_refs=("chunk:63",),
    )
    rich = _draft(
        "rich_product",
        title="What is the product?",
        question="What is this product?",
        answer=(
            "The product is a knowledge-base platform for business. "
            "It helps create a verifiable knowledge base, find duplicates, "
            "check retrieval quality, curate answers, and use knowledge in an assistant."
        ),
        source_refs=("chunk:1",),
    )
    unrelated = _draft(
        "pdf_upload",
        title="PDF upload",
        question="Can I upload PDF files?",
        answer="PDF files can be uploaded if text can be extracted.",
        source_refs=("chunk:9",),
    )

    clusters = _answer_slot_clusters(
        (short, unrelated, rich), local_relations=(), size=8
    )

    assert any(
        {item.candidate_key for item in cluster} >= {"short_product", "rich_product"}
        for cluster in clusters
    )


def test_answer_slot_clusters_use_local_duplicate_relations_without_text_overlap() -> (
    None
):
    left = _draft(
        "left",
        title="A",
        question="Primary question",
        answer="First answer.",
    )
    right = _draft(
        "right",
        title="B",
        question="Different wording",
        answer="Second answer.",
    )
    other = _draft(
        "other",
        title="PDF",
        question="Can I upload PDF files?",
        answer="PDF files can be uploaded.",
    )

    clusters = _answer_slot_clusters(
        (left, other, right),
        local_relations=(_relation("left", "right", "duplicates"),),
        size=8,
    )

    assert any(
        {item.candidate_key for item in cluster} >= {"left", "right"}
        for cluster in clusters
    )
