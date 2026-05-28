from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.retrieval_surface_compilation import (
    LocalSurfaceRelation,
    RetrievalSurfaceCandidate,
    RetrievalSurfaceDraft,
    RetrievalSurfaceRelation,
    SurfaceAnswerDraft,
    SurfaceGraphReconciliationRun,
    SurfaceQuestionReassignment,
    SurfaceRejectedQuestion,
)


class KnowledgeSurfaceCandidatePort(Protocol):
    async def save_surface_candidates(
        self,
        *,
        run_id: str,
        document_id: str,
        candidates: tuple[RetrievalSurfaceCandidate, ...],
    ) -> None: ...


class KnowledgeSurfaceAnswerDraftPort(Protocol):
    async def save_surface_answer_drafts(
        self,
        *,
        run_id: str,
        document_id: str,
        answer_drafts: tuple[SurfaceAnswerDraft, ...],
    ) -> None: ...


class KnowledgeSurfaceGraphRelationPort(Protocol):
    async def save_local_surface_relations(
        self,
        *,
        run_id: str,
        document_id: str,
        relations: tuple[LocalSurfaceRelation, ...],
    ) -> None: ...

    async def save_global_surface_relations(
        self,
        *,
        run_id: str,
        document_id: str,
        relations: tuple[RetrievalSurfaceRelation, ...],
    ) -> None: ...


class KnowledgeSurfaceGraphQuestionPort(Protocol):
    async def save_surface_rejected_questions(
        self,
        *,
        run_id: str,
        document_id: str,
        rejected_questions: tuple[SurfaceRejectedQuestion, ...],
    ) -> None: ...

    async def save_question_reassignments(
        self,
        *,
        run_id: str,
        document_id: str,
        reassignments: tuple[SurfaceQuestionReassignment, ...],
    ) -> None: ...


class KnowledgeSurfaceReconciliationPort(Protocol):
    async def save_surface_reconciliation_run(
        self,
        *,
        reconciliation_run: SurfaceGraphReconciliationRun,
    ) -> None: ...


class KnowledgeSurfaceCurationCardPort(Protocol):
    async def list_surface_cards_for_curation(
        self, *, project_id: str, document_id: str
    ) -> tuple[RetrievalSurfaceDraft, ...]: ...

    async def list_surface_graph_for_document(
        self, *, project_id: str, document_id: str
    ) -> tuple[RetrievalSurfaceRelation, ...]: ...
