from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotedQuestion,
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalRetrievalResult,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)


class WorkbenchRagEvalRepositoryPort(Protocol):
    async def create_run(self, *, run: WorkbenchRagEvalRun) -> WorkbenchRagEvalRun: ...

    async def list_published_entries_for_eval(
        self,
        *,
        project_id: str,
        publication_id: str | None,
        source_document_ref: str | None,
        limit: int,
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]: ...

    async def save_generated_questions(
        self,
        *,
        questions: tuple[WorkbenchRagEvalQuestion, ...],
    ) -> tuple[WorkbenchRagEvalQuestion, ...]: ...

    async def save_retrieval_results(
        self,
        *,
        results: tuple[WorkbenchRagEvalRetrievalResult, ...],
    ) -> tuple[WorkbenchRagEvalRetrievalResult, ...]: ...

    async def save_promoted_question_candidates(
        self,
        *,
        promotions: tuple[WorkbenchRagEvalPromotedQuestion, ...],
    ) -> tuple[WorkbenchRagEvalPromotedQuestion, ...]: ...

    async def complete_run(
        self,
        *,
        summary: WorkbenchRagEvalSummary,
    ) -> WorkbenchRagEvalSummary: ...

    async def get_latest_run(
        self,
        *,
        project_id: str,
    ) -> WorkbenchRagEvalSummary | None: ...

    async def get_run(
        self,
        *,
        run_id: str,
        project_id: str,
    ) -> WorkbenchRagEvalSummary | None: ...
