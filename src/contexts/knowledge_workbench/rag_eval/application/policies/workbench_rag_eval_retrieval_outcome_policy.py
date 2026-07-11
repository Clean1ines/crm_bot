from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalRetrievalClassification,
    WorkbenchRagEvalRetrievalOutcome,
)


class WorkbenchRagEvalRetrievalOutcomePolicy:
    def classify(
        self,
        *,
        expected_rank: int | None,
        expected_score: float | None,
        competitor_score: float | None,
        competitor_same_document: bool,
    ) -> WorkbenchRagEvalRetrievalClassification:
        if (
            competitor_same_document
            and competitor_score is not None
            and (expected_score is None or competitor_score > expected_score)
        ):
            return WorkbenchRagEvalRetrievalClassification.CONFUSION
        if expected_rank == 1:
            return WorkbenchRagEvalRetrievalClassification.PASS_STRONG
        if expected_rank is not None and expected_rank <= 3:
            return WorkbenchRagEvalRetrievalClassification.PASS_WEAK
        if expected_rank is not None and expected_rank <= 5:
            return WorkbenchRagEvalRetrievalClassification.CONFUSION
        return WorkbenchRagEvalRetrievalClassification.MISS

    def build(
        self,
        *,
        outcome_id: str,
        run_id: str,
        question_id: str,
        project_id: str,
        evaluation_stage: str,
        expected_runtime_entry_id: str,
        expected_fact_id: str,
        expected_rank: int | None,
        expected_score: float | None,
        best_competitor_runtime_entry_id: str | None,
        best_competitor_fact_id: str | None,
        best_competitor_score: float | None,
        competitor_same_document: bool,
        created_at: datetime | None = None,
    ) -> WorkbenchRagEvalRetrievalOutcome:
        competitor_score = best_competitor_score
        margin = (
            float(expected_score) - float(competitor_score)
            if expected_score is not None and competitor_score is not None
            else None
        )
        return WorkbenchRagEvalRetrievalOutcome(
            outcome_id=outcome_id,
            run_id=run_id,
            question_id=question_id,
            project_id=project_id,
            evaluation_stage=evaluation_stage,
            expected_runtime_entry_id=expected_runtime_entry_id,
            expected_fact_id=expected_fact_id,
            expected_rank=expected_rank,
            expected_score=expected_score,
            best_competitor_runtime_entry_id=best_competitor_runtime_entry_id,
            best_competitor_fact_id=best_competitor_fact_id,
            best_competitor_score=best_competitor_score,
            score_margin=margin,
            classification=self.classify(
                expected_rank=expected_rank,
                expected_score=expected_score,
                competitor_score=competitor_score,
                competitor_same_document=competitor_same_document,
            ),
            created_at=created_at or datetime.now(timezone.utc),
        )
