from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_promotion_application_errors import (
    WorkbenchRagEvalPromotionConflictCode,
    WorkbenchRagEvalPromotionConflictError,
    WorkbenchRagEvalPromotionEmbeddingError,
    WorkbenchRagEvalPromotionNotFoundError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalPromotionApplicationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotions_batch import (
    ApplyWorkbenchRagEvalPromotionsBatch,
)


@dataclass(slots=True)
class ApplyWorkbenchRagEvalPromotion:
    grouped_application: ApplyWorkbenchRagEvalPromotionsBatch

    async def execute(
        self,
        *,
        project_id: str,
        promotion_id: str,
        applied_at: datetime,
    ) -> WorkbenchRagEvalPromotionApplicationResult:
        result = await self.grouped_application.execute(
            project_id=project_id,
            mode="selected",
            promotion_ids=(promotion_id,),
            run_id=None,
            applied_at=applied_at,
        )
        if result.errors:
            error = result.errors[0]
            if error.code == "not_found":
                raise WorkbenchRagEvalPromotionNotFoundError(error.message)
            if error.code == "embedding_failed":
                raise WorkbenchRagEvalPromotionEmbeddingError(error.message)
            try:
                code = WorkbenchRagEvalPromotionConflictCode(error.code)
            except ValueError:
                code = WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT
            raise WorkbenchRagEvalPromotionConflictError(
                error.message,
                code=code,
                promotion_ids=error.promotion_ids,
                runtime_entry_id=error.runtime_entry_id,
            )
        return result


__all__ = [
    "ApplyWorkbenchRagEvalPromotion",
    "WorkbenchRagEvalPromotionConflictCode",
    "WorkbenchRagEvalPromotionConflictError",
    "WorkbenchRagEvalPromotionEmbeddingError",
    "WorkbenchRagEvalPromotionNotFoundError",
]
