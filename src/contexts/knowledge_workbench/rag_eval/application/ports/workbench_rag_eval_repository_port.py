from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotedQuestion,
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionApplyResult,
    WorkbenchRagEvalPromotionCandidateDetails,
    WorkbenchRagEvalQuestionDetails,
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalRetrievalResult,
    WorkbenchRagEvalRetrievalOutcome,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)


class WorkbenchRagEvalRepositoryPort(Protocol):
    async def materialize_baseline_questions(
        self, *, run_id: str, project_id: str, created_at: datetime
    ) -> int: ...

    async def create_run(self, *, run: WorkbenchRagEvalRun) -> WorkbenchRagEvalRun: ...

    async def transition_run_progress(
        self,
        *,
        run_id: str,
        project_id: str,
        status: WorkbenchRagEvalRunStatus,
        current_phase: WorkbenchRagEvalCurrentPhase,
        progress: WorkbenchRagEvalRunProgress,
        updated_at: datetime,
        blocked_reason: str | None = None,
        failed_reason: str | None = None,
        capacity_next_due_at: datetime | None = None,
        capacity_model_ref: str | None = None,
        capacity_account_ref: str | None = None,
    ) -> None: ...

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

    async def save_question_roles(
        self, *, roles: Mapping[str, WorkbenchRagEvalQuestionRole]
    ) -> None: ...

    async def save_retrieval_outcomes(
        self, *, outcomes: tuple[WorkbenchRagEvalRetrievalOutcome, ...]
    ) -> tuple[WorkbenchRagEvalRetrievalOutcome, ...]: ...

    async def mark_questions_evaluated(
        self,
        *,
        run_id: str,
        question_ids: tuple[str, ...],
        evaluated_at: datetime,
    ) -> None: ...

    async def complete_initial_retrieval_evaluation(
        self,
        *,
        run_id: str,
        project_id: str,
        total_questions: int,
        classification_counts: Mapping[str, int],
        updated_at: datetime,
    ) -> None: ...

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

    async def list_run_questions(
        self,
        *,
        project_id: str,
        run_id: str,
    ) -> tuple[WorkbenchRagEvalQuestionDetails, ...]: ...

    async def list_run_promotion_candidates(
        self,
        *,
        project_id: str,
        run_id: str,
    ) -> tuple[WorkbenchRagEvalPromotionCandidateDetails, ...]: ...

    async def get_promotion_candidate(
        self,
        *,
        project_id: str,
        promotion_id: str,
    ) -> WorkbenchRagEvalPromotionCandidateDetails | None: ...

    async def get_promotion_application_target(
        self,
        *,
        project_id: str,
        promotion_id: str,
    ) -> WorkbenchRagEvalPromotionApplicationTarget | None: ...

    async def list_promotion_application_targets_for_ids(
        self,
        *,
        project_id: str,
        promotion_ids: Sequence[str],
    ) -> tuple[WorkbenchRagEvalPromotionApplicationTarget, ...]: ...

    async def list_promotion_application_targets_for_run(
        self,
        *,
        project_id: str,
        run_id: str,
    ) -> tuple[WorkbenchRagEvalPromotionApplicationTarget, ...]: ...

    async def apply_promotion_candidates_for_target(
        self,
        *,
        project_id: str,
        promotion_ids: Sequence[str],
        target_runtime_entry_id: str,
        embedding_model_id: str,
        dimensions: int,
        embedding: Sequence[float],
        embedding_text: str,
        embedding_text_hash: str,
        applied_at: datetime,
    ) -> tuple[WorkbenchRagEvalPromotionApplyResult, ...]: ...

    async def apply_promotion_candidate(
        self,
        *,
        project_id: str,
        promotion_id: str,
        embedding_model_id: str,
        dimensions: int,
        embedding: Sequence[float],
        embedding_text: str,
        embedding_text_hash: str,
        applied_at: datetime,
    ) -> WorkbenchRagEvalPromotionApplyResult: ...
