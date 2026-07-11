import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_review_transition_policy import (
    WorkbenchRagEvalPromotionReviewTransitionConflictError,
    WorkbenchRagEvalPromotionReviewTransitionPolicy,
)


@pytest.mark.parametrize(
    ("current", "requested", "changed"),
    (
        (
            WorkbenchRagEvalPromotionStatus.CANDIDATE,
            WorkbenchRagEvalPromotionStatus.APPROVED,
            True,
        ),
        (
            WorkbenchRagEvalPromotionStatus.CANDIDATE,
            WorkbenchRagEvalPromotionStatus.REJECTED,
            True,
        ),
        (
            WorkbenchRagEvalPromotionStatus.APPROVED,
            WorkbenchRagEvalPromotionStatus.APPROVED,
            False,
        ),
        (
            WorkbenchRagEvalPromotionStatus.REJECTED,
            WorkbenchRagEvalPromotionStatus.REJECTED,
            False,
        ),
    ),
)
def test_review_transition_allows_valid_and_idempotent_transitions(
    current: WorkbenchRagEvalPromotionStatus,
    requested: WorkbenchRagEvalPromotionStatus,
    changed: bool,
) -> None:
    transition = WorkbenchRagEvalPromotionReviewTransitionPolicy().transition(
        current_status=current,
        requested_status=requested,
    )

    assert transition.changed is changed
    assert transition.current_status is current
    assert transition.requested_status is requested


@pytest.mark.parametrize(
    ("current", "requested"),
    (
        (
            WorkbenchRagEvalPromotionStatus.APPROVED,
            WorkbenchRagEvalPromotionStatus.REJECTED,
        ),
        (
            WorkbenchRagEvalPromotionStatus.REJECTED,
            WorkbenchRagEvalPromotionStatus.APPROVED,
        ),
        *(
            (status, WorkbenchRagEvalPromotionStatus.APPROVED)
            for status in (
                WorkbenchRagEvalPromotionStatus.APPLYING,
                WorkbenchRagEvalPromotionStatus.APPLIED,
                WorkbenchRagEvalPromotionStatus.SUPERSEDED,
                WorkbenchRagEvalPromotionStatus.REGRESSION_FAILED,
                WorkbenchRagEvalPromotionStatus.ROLLED_BACK,
            )
        ),
        *(
            (status, WorkbenchRagEvalPromotionStatus.REJECTED)
            for status in (
                WorkbenchRagEvalPromotionStatus.APPLYING,
                WorkbenchRagEvalPromotionStatus.APPLIED,
                WorkbenchRagEvalPromotionStatus.SUPERSEDED,
                WorkbenchRagEvalPromotionStatus.REGRESSION_FAILED,
                WorkbenchRagEvalPromotionStatus.ROLLED_BACK,
            )
        ),
    ),
)
def test_review_transition_rejects_incompatible_state(
    current: WorkbenchRagEvalPromotionStatus,
    requested: WorkbenchRagEvalPromotionStatus,
) -> None:
    with pytest.raises(WorkbenchRagEvalPromotionReviewTransitionConflictError):
        WorkbenchRagEvalPromotionReviewTransitionPolicy().transition(
            current_status=current,
            requested_status=requested,
        )
