from __future__ import annotations

from src.application.dto.knowledge_surface_card_dto import SurfaceCardDto
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceDraft,
    RetrievalSurfaceRelation,
    SurfaceQuestionOwnership,
    SurfaceQuestionReassignment,
)


def _surface(key: str, *, kind: str = "umbrella") -> RetrievalSurfaceDraft:
    return RetrievalSurfaceDraft(
        id=f"surface-{key}",
        run_id="run-1",
        document_id="doc-1",
        local_surface_key=key,
        title="База знаний" if key == "knowledge_base" else "Загрузка PDF",
        canonical_question="Что включает база знаний?",
        surface_kind=kind,  # type: ignore[arg-type]
        answer_scope="Обзорная область ответа.",
        question_scope="Только обзорные вопросы.",
        exclusion_scope="Не отвечать на вопросы дочерних карточек.",
        answer="Обзор базы знаний с упоминанием загрузки PDF.",
        short_answer="Обзор базы знаний.",
        status="draft",
        publication_status="unpublished",
        source_refs=("chunk:0",),
        source_excerpt="source",
        confidence=0.9,
    )


def test_surface_card_dto_returns_graph_context_for_umbrella_card() -> None:
    card = SurfaceCardDto.from_surface_graph(
        surface=_surface("knowledge_base"),
        relations=(
            RetrievalSurfaceRelation(
                id="relation-1",
                run_id="run-1",
                document_id="doc-1",
                parent_surface_key="knowledge_base",
                child_surface_key="pdf_upload",
                relation_type="umbrella_contains",
                reason="PDF upload is a child-specific surface.",
                confidence=0.9,
            ),
        ),
        ownership=(
            SurfaceQuestionOwnership(
                id="ownership-1",
                run_id="run-1",
                document_id="doc-1",
                question="что включает база знаний?",
                owner_surface_key="knowledge_base",
                question_kind="faq_question",
                confidence=0.91,
                reason="overview scope",
            ),
        ),
        reassignments=(
            SurfaceQuestionReassignment(
                id="reassign-1",
                run_id="run-1",
                document_id="doc-1",
                question="можно ли загрузить PDF?",
                from_surface_key="knowledge_base",
                to_surface_key="pdf_upload",
                reason="child surface answers this more precisely",
                confidence=0.95,
            ),
        ),
    )

    payload = card.to_dict()

    assert payload["local_surface_key"] == "knowledge_base"
    assert payload["surface_kind"] == "umbrella"
    assert payload["child_surfaces"] == [
        {
            "surface_key": "pdf_upload",
            "relation_type": "umbrella_contains",
            "reason": "PDF upload is a child-specific surface.",
        }
    ]
    assert payload["owned_questions"] == [
        {
            "question": "что включает база знаний?",
            "question_kind": "faq_question",
            "confidence": 0.91,
            "source": "compiled",
        }
    ]
    assert payload["rejected_questions"] == [
        {
            "question": "можно ли загрузить PDF?",
            "belongs_to_surface_key": "pdf_upload",
            "reason": "child surface answers this more precisely",
            "confidence": 0.95,
        }
    ]
    assert any("зонтичной" in warning for warning in payload["quality_warnings"])


def test_surface_card_dto_links_child_to_parent() -> None:
    card = SurfaceCardDto.from_surface_graph(
        surface=_surface("pdf_upload", kind="specific"),
        relations=(
            RetrievalSurfaceRelation(
                id="relation-1",
                run_id="run-1",
                document_id="doc-1",
                parent_surface_key="knowledge_base",
                child_surface_key="pdf_upload",
                relation_type="umbrella_contains",
                reason="PDF upload belongs to knowledge base area.",
                confidence=0.9,
            ),
        ),
        ownership=(),
    )

    payload = card.to_dict()

    assert payload["parent_surfaces"] == [
        {
            "surface_key": "knowledge_base",
            "relation_type": "umbrella_contains",
            "reason": "PDF upload belongs to knowledge base area.",
        }
    ]
    assert payload["child_surfaces"] == []
    assert payload["quality_warnings"] == []
