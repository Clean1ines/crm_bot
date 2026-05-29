from __future__ import annotations

from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCandidate,
    RetrievalSurfaceMergeDecision,
    SurfaceAnswerDraft,
    SurfaceQuestionOwnershipDecision,
)
from src.infrastructure.llm.knowledge_surface_full_graph_compiler import (
    _filter_merged_relations,
    _final_ownership,
    _final_surfaces,
    _reassign_merged_surface_questions,
)


def _candidate(key: str) -> RetrievalSurfaceCandidate:
    return RetrievalSurfaceCandidate(
        id=f"candidate-{key}",
        run_id="run-1",
        document_id="doc-1",
        source_unit_id="unit-1",
        local_surface_key=key,
        provisional_title=key,
        surface_kind="specific",
        answer_scope="",
        question_scope="",
        exclusion_scope="",
        parent_candidate_keys=(),
        child_candidate_keys=(),
        sibling_candidate_keys=(),
        source_refs=("chunks: 1",),
        confidence=0.8,
    )


def _draft(key: str, *, question: str, answer: str) -> SurfaceAnswerDraft:
    return SurfaceAnswerDraft(
        id=f"draft-{key}",
        run_id="run-1",
        document_id="doc-1",
        candidate_key=key,
        title=question,
        canonical_question=question,
        short_answer=answer,
        answer=answer,
        answer_scope="",
        question_scope=question,
        exclusion_scope="",
        source_refs=("chunks: 1",),
        warnings=(),
        metadata={"customer_intent": question, "factual_answer_core": answer},
    )


def _merge() -> RetrievalSurfaceMergeDecision:
    return RetrievalSurfaceMergeDecision(
        id="merge-1",
        run_id="run-1",
        document_id="doc-1",
        survivor_surface_key="survivor",
        merged_surface_keys=("merged",),
        keep_separate_surface_keys=(),
        decision_type="merge",
        reason="same customer intent and factual answer",
        confidence=0.95,
    )


def test_merge_decision_is_authoritative_for_visible_final_surfaces() -> None:
    surfaces = _final_surfaces(
        run_id="run-1",
        document_id="doc-1",
        candidates=(_candidate("survivor"), _candidate("merged")),
        drafts=(
            _draft(
                "survivor",
                question="Что делает сервис?",
                answer="Он отвечает на вопросы.",
            ),
            _draft(
                "merged",
                question="Как работает сервис?",
                answer="Он отвечает на вопросы.",
            ),
        ),
        warnings=(),
        merge_decisions=(_merge(),),
    )

    assert [surface.local_surface_key for surface in surfaces] == ["survivor"]
    assert surfaces[0].metadata["merge_decision_applied"] is True
    assert surfaces[0].metadata["merged_surface_keys"] == ["merged"]
    assert "Как работает сервис?" in surfaces[0].question_scope


def test_questions_from_merged_surface_are_reassigned_to_survivor() -> None:
    ownership = (
        SurfaceQuestionOwnershipDecision(
            id="owned-1",
            run_id="run-1",
            document_id="doc-1",
            surface_key="merged",
            question="Как работает сервис?",
            question_kind="faq_question",
            ownership_confidence=0.91,
            source="test",
            status="owned",
        ),
    )

    reassignments = _reassign_merged_surface_questions(
        run_id="run-1",
        document_id="doc-1",
        ownership_decisions=ownership,
        merge_decisions=(_merge(),),
    )
    final = _final_ownership(
        run_id="run-1",
        document_id="doc-1",
        decisions=ownership,
        reassignments=reassignments,
    )

    assert reassignments[0].from_surface_key == "merged"
    assert reassignments[0].to_surface_key == "survivor"
    assert final == ()


def test_relations_to_merged_surfaces_are_not_visible() -> None:
    from src.domain.project_plane.retrieval_surface_compilation import (
        RetrievalSurfaceRelation,
    )

    relations = (
        RetrievalSurfaceRelation(
            id="rel-1",
            run_id="run-1",
            document_id="doc-1",
            parent_surface_key="survivor",
            child_surface_key="merged",
            relation_type="duplicates",
            reason="same answer",
            confidence=0.9,
        ),
    )

    assert _filter_merged_relations(relations, merge_decisions=(_merge(),)) == ()
