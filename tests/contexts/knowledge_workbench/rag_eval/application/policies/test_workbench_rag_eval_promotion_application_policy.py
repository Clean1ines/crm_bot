from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    WorkbenchRagEvalPromotionApplicationCandidate,
    WorkbenchRagEvalPromotionApplicationSnapshot,
    stable_runtime_snapshot_hash,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_application_policy import (
    WorkbenchRagEvalPromotionApplicationConflictCode,
    WorkbenchRagEvalPromotionApplicationDecisionCode,
    WorkbenchRagEvalPromotionApplicationPolicy,
    WorkbenchRagEvalPromotionApplicationPolicyConfig,
    WorkbenchRagEvalPromotionApplicationPolicyConflictError,
)


VECTOR_384 = (0.0,) * WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS


def _candidate(
    promotion_id: str,
    *,
    question: str = "New alias?",
    status: WorkbenchRagEvalPromotionStatus = WorkbenchRagEvalPromotionStatus.APPROVED,
) -> WorkbenchRagEvalPromotionApplicationCandidate:
    return WorkbenchRagEvalPromotionApplicationCandidate(
        promotion_id=promotion_id,
        run_id="run-1",
        question_id=f"question-{promotion_id}",
        target_fact_id="fact-1",
        question=question,
        status=status,
    )


def _snapshot(
    *,
    possible_questions: tuple[str, ...] = ("Existing?",),
    active_promoted_questions: tuple[str, ...] = (),
    candidates: tuple[WorkbenchRagEvalPromotionApplicationCandidate, ...] = (
        _candidate("promotion-1"),
    ),
    runtime_status: str = "active",
    runtime_visibility: str = "published",
    active_revision_id: str | None = None,
) -> WorkbenchRagEvalPromotionApplicationSnapshot:
    embedding_text = "Claim:\nClaim text\n\nPossible questions:\n- Existing?"
    return WorkbenchRagEvalPromotionApplicationSnapshot(
        project_id="project-1",
        runtime_entry_id="entry-1",
        fact_id="fact-1",
        runtime_status=runtime_status,
        runtime_visibility=runtime_visibility,
        claim="Claim text",
        possible_questions=possible_questions,
        active_promoted_questions=active_promoted_questions,
        exclusion_scope=None,
        embedding_text=embedding_text,
        embedding=VECTOR_384,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        candidates=candidates,
        runtime_hash=stable_runtime_snapshot_hash(
            possible_questions=possible_questions,
            embedding_text=embedding_text,
            embedding=VECTOR_384,
            embedding_model_id="model-1",
            embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        ),
        active_revision_id=active_revision_id,
    )


def _policy(limit: int = 12) -> WorkbenchRagEvalPromotionApplicationPolicy:
    return WorkbenchRagEvalPromotionApplicationPolicy(
        config=WorkbenchRagEvalPromotionApplicationPolicyConfig(
            max_active_promoted_questions_per_runtime_entry=limit,
        )
    )


def test_approved_candidate_is_accepted() -> None:
    decision = _policy().decide(_snapshot())
    assert decision.code is WorkbenchRagEvalPromotionApplicationDecisionCode.APPLY
    assert tuple(item.promotion_id for item in decision.applicable_candidates) == (
        "promotion-1",
    )


@pytest.mark.parametrize(
    "status",
    [
        WorkbenchRagEvalPromotionStatus.CANDIDATE,
        WorkbenchRagEvalPromotionStatus.REJECTED,
        WorkbenchRagEvalPromotionStatus.SUPERSEDED,
        WorkbenchRagEvalPromotionStatus.REGRESSION_FAILED,
        WorkbenchRagEvalPromotionStatus.ROLLED_BACK,
    ],
)
def test_non_approved_candidate_is_rejected(
    status: WorkbenchRagEvalPromotionStatus,
) -> None:
    with pytest.raises(WorkbenchRagEvalPromotionApplicationPolicyConflictError):
        _policy().decide(
            _snapshot(candidates=(_candidate("promotion-1", status=status),))
        )


def test_ten_baseline_aliases_plus_three_promoted_aliases_is_allowed() -> None:
    baseline = tuple(f"Baseline {index}?" for index in range(10))
    active_promoted = tuple(f"Promoted {index}?" for index in range(3))
    decision = _policy().decide(
        _snapshot(
            possible_questions=(*baseline, *active_promoted),
            active_promoted_questions=active_promoted,
            candidates=(_candidate("promotion-1", question="Fourth promoted?"),),
        )
    )
    assert decision.should_apply is True
    assert len(decision.new_possible_questions) == 14


def test_twelve_active_promoted_aliases_and_zero_new_has_no_conflict() -> None:
    active_promoted = tuple(f"Promoted {index}?" for index in range(12))
    decision = _policy().decide(
        _snapshot(
            possible_questions=active_promoted,
            active_promoted_questions=active_promoted,
            candidates=(_candidate("promotion-1", question=" Promoted 0!!! "),),
        )
    )
    assert decision.should_apply is False
    assert (
        decision.code is WorkbenchRagEvalPromotionApplicationDecisionCode.NO_NEW_ALIASES
    )


def test_eleven_active_promoted_plus_one_new_is_allowed() -> None:
    active_promoted = tuple(f"Promoted {index}?" for index in range(11))
    decision = _policy().decide(
        _snapshot(
            possible_questions=active_promoted,
            active_promoted_questions=active_promoted,
            candidates=(_candidate("promotion-1", question="Promoted 11?"),),
        )
    )
    assert decision.should_apply is True


def test_twelve_active_promoted_plus_one_new_is_rejected() -> None:
    active_promoted = tuple(f"Promoted {index}?" for index in range(12))
    with pytest.raises(
        WorkbenchRagEvalPromotionApplicationPolicyConflictError
    ) as exc_info:
        _policy().decide(
            _snapshot(
                possible_questions=active_promoted,
                active_promoted_questions=active_promoted,
                candidates=(_candidate("promotion-1", question="Promoted 12?"),),
            )
        )
    assert exc_info.value.code is (
        WorkbenchRagEvalPromotionApplicationConflictCode.ALIAS_LIMIT_EXCEEDED
    )


def test_duplicate_new_candidate_consumes_one_promoted_slot() -> None:
    active_promoted = tuple(f"Promoted {index}?" for index in range(11))
    decision = _policy().decide(
        _snapshot(
            possible_questions=active_promoted,
            active_promoted_questions=active_promoted,
            candidates=(
                _candidate("promotion-2", question="Final alias?"),
                _candidate("promotion-1", question=" FINAL ALIAS!!! "),
            ),
        )
    )
    assert tuple(item.promotion_id for item in decision.applicable_candidates) == (
        "promotion-1",
    )
    assert tuple(item.promotion_id for item in decision.skipped_candidates) == (
        "promotion-2",
    )


def test_existing_baseline_duplicate_is_skipped_without_consuming_promoted_slot() -> (
    None
):
    baseline = tuple(f"Baseline {index}?" for index in range(20))
    active_promoted = tuple(f"Promoted {index}?" for index in range(12))
    decision = _policy().decide(
        _snapshot(
            possible_questions=(*baseline, *active_promoted),
            active_promoted_questions=active_promoted,
            candidates=(_candidate("promotion-1", question=" BASELINE 0!!! "),),
        )
    )
    assert decision.should_apply is False
    assert decision.skipped_candidates[0].code is (
        WorkbenchRagEvalPromotionApplicationDecisionCode.EXISTING_ALIAS
    )


def test_non_applied_lifecycle_rows_are_not_part_of_active_promoted_count() -> None:
    active_promoted = tuple(f"Promoted {index}?" for index in range(11))
    decision = _policy().decide(
        _snapshot(
            possible_questions=active_promoted,
            active_promoted_questions=active_promoted,
            candidates=(_candidate("promotion-1", question="Twelfth?"),),
        )
    )
    assert decision.should_apply is True
    assert len(active_promoted) + len(decision.applicable_candidates) == 12


def test_active_revision_conflicts_before_claim_or_embedding() -> None:
    with pytest.raises(
        WorkbenchRagEvalPromotionApplicationPolicyConflictError
    ) as exc_info:
        _policy().decide(_snapshot(active_revision_id="revision-1"))
    assert exc_info.value.code is (
        WorkbenchRagEvalPromotionApplicationConflictCode.ACTIVE_REVISION
    )


@pytest.mark.parametrize(
    ("runtime_status", "runtime_visibility"),
    [("inactive", "published"), ("active", "draft")],
)
def test_inactive_or_unpublished_target_conflicts(
    runtime_status: str,
    runtime_visibility: str,
) -> None:
    with pytest.raises(WorkbenchRagEvalPromotionApplicationPolicyConflictError):
        _policy().decide(
            _snapshot(
                runtime_status=runtime_status,
                runtime_visibility=runtime_visibility,
            )
        )
