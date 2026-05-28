from __future__ import annotations

from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCandidate,
    RetrievalSurfaceSourceChild,
    RetrievalSurfaceSourceUnit,
    SurfaceAnswerDraft,
    SurfaceQuestionOwnershipDecision,
)


def unit(body: str = "FAQ body") -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(
        id="unit-1",
        run_id="run-1",
        document_id="doc-1",
        source_unit_key="unit:key",
        source_chunk_indexes=(0,),
        title="FAQ unit",
        body=body,
        children=(
            RetrievalSurfaceSourceChild(
                title="content",
                body=body,
                raw_text=body,
                label_kind="content_section",
            ),
        ),
        raw_text=body,
        section_path=("Root",),
        source_refs=("chunk:0",),
        preprocessing_mode="faq",
        metadata={},
    )


def candidate(key: str, *, source_unit_id: str = "unit-1") -> RetrievalSurfaceCandidate:
    return RetrievalSurfaceCandidate(
        id=f"candidate:{key}",
        run_id="run-1",
        document_id="doc-1",
        source_unit_id=source_unit_id,
        local_surface_key=key,
        provisional_title=f"Candidate {key}",
        surface_kind="specific",
        answer_scope="scope",
        question_scope="question scope",
        exclusion_scope="",
        parent_candidate_keys=(),
        child_candidate_keys=(),
        sibling_candidate_keys=(),
        source_refs=("chunk:0",),
        confidence=0.86,
        metadata={},
    )


def draft(
    key: str,
    *,
    title: str = "Delivery",
    canonical_question: str = "How does delivery work?",
    answer: str | None = None,
    source_refs: tuple[str, ...] = ("chunk:0",),
) -> SurfaceAnswerDraft:
    answer_text = answer or f"Answer for {key}"
    return SurfaceAnswerDraft(
        id=f"draft:{key}",
        run_id="run-1",
        document_id="doc-1",
        candidate_key=key,
        title=title,
        canonical_question=canonical_question,
        short_answer=answer_text,
        answer=answer_text,
        answer_scope="scope",
        question_scope="question scope",
        exclusion_scope="",
        source_refs=source_refs,
        warnings=(),
        metadata={},
    )


def ownership(
    key: str,
    question: str = "How does delivery work?",
) -> SurfaceQuestionOwnershipDecision:
    return SurfaceQuestionOwnershipDecision(
        id=f"ownership:{key}",
        run_id="run-1",
        document_id="doc-1",
        surface_key=key,
        question=question,
        question_kind="faq_question",
        ownership_confidence=0.9,
        source="test",
        status="owned",
    )
