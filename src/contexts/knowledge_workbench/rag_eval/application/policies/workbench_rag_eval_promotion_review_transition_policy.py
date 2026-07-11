from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)


class WorkbenchRagEvalPromotionReviewTransitionConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionReviewTransition:
    current_status: WorkbenchRagEvalPromotionStatus
    requested_status: WorkbenchRagEvalPromotionStatus
    changed: bool


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionReviewTransitionPolicy:
    def transition(
        self,
        *,
        current_status: WorkbenchRagEvalPromotionStatus,
        requested_status: WorkbenchRagEvalPromotionStatus,
    ) -> WorkbenchRagEvalPromotionReviewTransition:
        if requested_status not in (
            WorkbenchRagEvalPromotionStatus.APPROVED,
            WorkbenchRagEvalPromotionStatus.REJECTED,
        ):
            raise ValueError("requested status must be approved or rejected")

        if current_status is requested_status:
            return WorkbenchRagEvalPromotionReviewTransition(
                current_status=current_status,
                requested_status=requested_status,
                changed=False,
            )

        if current_status is WorkbenchRagEvalPromotionStatus.CANDIDATE:
            return WorkbenchRagEvalPromotionReviewTransition(
                current_status=current_status,
                requested_status=requested_status,
                changed=True,
            )

        raise WorkbenchRagEvalPromotionReviewTransitionConflictError(
            "Promotion candidate cannot transition "
            f"from {current_status.value} to {requested_status.value}"
        )
