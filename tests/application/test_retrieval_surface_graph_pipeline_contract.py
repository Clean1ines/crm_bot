from __future__ import annotations

from src.application.services.knowledge_surface_graph_quality import (
    validate_faq_surface_graph_quality,
)
from src.domain.project_plane.knowledge_preprocessing import MODE_FAQ
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceDraft,
    RetrievalSurfaceGraph,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceUnit,
    SurfaceQuestionOwnership,
)


def _source_unit(index: int) -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(
        id=f"unit-{index}",
        run_id="run-1",
        document_id="doc-1",
        source_unit_key=f"unit-{index}",
        source_chunk_indexes=(index,),
        title=f"Unit {index}",
        body=f"Body {index}",
        children=(),
        raw_text=f"Body {index}",
        section_path=(f"Unit {index}",),
        source_refs=(f"chunk:{index}",),
        preprocessing_mode=MODE_FAQ,
    )


def _surface(key: str, *, kind: str = "specific", answer: str = "Answer") -> RetrievalSurfaceDraft:
    return RetrievalSurfaceDraft(
        id=f"surface-{key}",
        run_id="run-1",
        document_id="doc-1",
        local_surface_key=key,
        title=key,
        canonical_question=f"What is {key}?",
        surface_kind=kind,  # type: ignore[arg-type]
        answer_scope=f"Answer scope for {key}",
        question_scope=f"Question scope for {key}",
        exclusion_scope=f"Exclusion scope for {key}",
        answer=answer,
        short_answer=answer[:100],
        status="draft",
        publication_status="unpublished",
        source_refs=("chunk:0",),
        source_excerpt=answer,
        confidence=0.9,
    )


def _relation(parent: str, child: str) -> RetrievalSurfaceRelation:
    return RetrievalSurfaceRelation(
        id=f"relation-{parent}-{child}",
        run_id="run-1",
        document_id="doc-1",
        parent_surface_key=parent,
        child_surface_key=child,
        relation_type="umbrella_contains",
        reason="parent child",
        confidence=0.9,
    )


def _ownership(owner: str, question: str, rejected_from: tuple[str, ...] = ()) -> SurfaceQuestionOwnership:
    return SurfaceQuestionOwnership(
        id=f"ownership-{owner}-{question}",
        run_id="run-1",
        document_id="doc-1",
        question=question,
        owner_surface_key=owner,
        question_kind="faq_question",
        confidence=0.9,
        reason="scope match",
        rejected_from_surface_keys=rejected_from,
    )


def _graph(
    *,
    source_unit_count: int,
    surfaces: tuple[RetrievalSurfaceDraft, ...],
    relations: tuple[RetrievalSurfaceRelation, ...] = (),
    ownership: tuple[SurfaceQuestionOwnership, ...] = (),
) -> RetrievalSurfaceGraph:
    return RetrievalSurfaceGraph(
        run_id="run-1",
        document_id="doc-1",
        source_units=tuple(_source_unit(index) for index in range(source_unit_count)),
        surfaces=surfaces,
        relations=relations,
        ownership=ownership,
        reassignments=(),
        merge_decisions=(),
    )


def test_large_document_cannot_collapse_to_two_generic_surfaces() -> None:
    result = validate_faq_surface_graph_quality(
        _graph(
            source_unit_count=49,
            surfaces=(
                _surface("generic_overview", kind="umbrella"),
                _surface("generic_details", kind="standalone"),
            ),
            relations=(_relation("generic_overview", "generic_details"),),
            ownership=(_ownership("generic_details", "Что это?", ("generic_overview",)),),
        )
    )

    assert not result.passed
    assert "large_document_collapsed_to_too_few_surfaces" in result.issues
    assert "large_document_final_surface_count_too_low" in result.issues
    assert result.metrics["quality_status"] == "failed"


def test_surface_answer_count_zero_fails_quality_gate() -> None:
    result = validate_faq_surface_graph_quality(
        _graph(
            source_unit_count=2,
            surfaces=(_surface("empty", answer=""),),
        )
    )

    assert not result.passed
    assert "no_surface_answers" in result.issues


def test_multi_surface_graph_requires_relations() -> None:
    result = validate_faq_surface_graph_quality(
        _graph(
            source_unit_count=2,
            surfaces=(
                _surface("one"),
                _surface("two"),
            ),
        )
    )

    assert not result.passed
    assert "missing_relations_for_multi_surface_graph" in result.issues


def test_umbrella_surface_does_not_own_child_questions() -> None:
    result = validate_faq_surface_graph_quality(
        _graph(
            source_unit_count=2,
            surfaces=(
                _surface("knowledge_base", kind="umbrella"),
                _surface("pdf_upload", kind="specific"),
            ),
            relations=(_relation("knowledge_base", "pdf_upload"),),
            ownership=(
                _ownership("knowledge_base", "можно ли загрузить PDF?"),
                _ownership("pdf_upload", "можно ли загрузить PDF?"),
            ),
        )
    )

    assert not result.passed
    assert "umbrella_owns_child_specific_questions" in result.issues


def test_parent_child_without_rejected_questions_warns_but_can_pass() -> None:
    result = validate_faq_surface_graph_quality(
        _graph(
            source_unit_count=2,
            surfaces=(
                _surface("knowledge_base", kind="umbrella"),
                _surface("pdf_upload", kind="specific"),
            ),
            relations=(_relation("knowledge_base", "pdf_upload"),),
            ownership=(
                _ownership("knowledge_base", "что включает база знаний?"),
                _ownership("pdf_upload", "можно ли загрузить PDF?"),
            ),
        )
    )

    assert result.passed
    assert "ownership_not_discriminative" in result.warnings


def test_parent_child_relation_is_not_duplicate_merge() -> None:
    result = validate_faq_surface_graph_quality(
        _graph(
            source_unit_count=2,
            surfaces=(
                _surface("knowledge_base", kind="umbrella"),
                _surface("pdf_upload", kind="specific"),
            ),
            relations=(_relation("knowledge_base", "pdf_upload"),),
            ownership=(
                _ownership("knowledge_base", "что включает база знаний?"),
                _ownership("pdf_upload", "можно ли загрузить PDF?", ("knowledge_base",)),
            ),
        )
    )

    assert result.passed
    assert not result.issues
}
