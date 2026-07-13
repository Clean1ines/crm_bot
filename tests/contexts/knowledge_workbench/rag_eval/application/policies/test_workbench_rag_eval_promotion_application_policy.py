from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
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
    candidates: tuple[WorkbenchRagEvalPromotionApplicationCandidate, ...] = (
        _candidate("promotion-1"),
    ),
    possible_questions: tuple[str, ...] = ("Existing?",),
    runtime_status: str = "active",
    runtime_visibility: str = "published",
    active_revision_id: str | None = None,
) -> WorkbenchRagEvalPromotionApplicationSnapshot:
    embedding = (0.1, 0.2, 0.3)
    embedding_text = "Claim:\nClaim text\n\nPossible questions:\n- Existing?"
    return WorkbenchRagEvalPromotionApplicationSnapshot(
        project_id="project-1",
        runtime_entry_id="entry-1",
        fact_id="fact-1",
        runtime_status=runtime_status,
        runtime_visibility=runtime_visibility,
        claim="Claim text",
        possible_questions=possible_questions,
        exclusion_scope=None,
        embedding_text=embedding_text,
        embedding=embedding,
        embedding_model_id="model-1",
        embedding_dimensions=3,
        candidates=candidates,
        runtime_hash=stable_runtime_snapshot_hash(
            possible_questions=possible_questions,
            embedding_text=embedding_text,
            embedding=embedding,
            embedding_model_id="model-1",
            embedding_dimensions=3,
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


def test_existing_alias_is_skipped_without_new_embedding_surface() -> None:
    decision = _policy().decide(
        _snapshot(candidates=(_candidate("promotion-1", question=" EXISTING!!! "),))
    )
    assert (
        decision.code is WorkbenchRagEvalPromotionApplicationDecisionCode.NO_NEW_ALIASES
    )
    assert decision.applicable_candidates == ()
    assert decision.skipped_candidates[0].code is (
        WorkbenchRagEvalPromotionApplicationDecisionCode.EXISTING_ALIAS
    )


def test_duplicate_selected_alias_is_deduplicated_deterministically() -> None:
    decision = _policy().decide(
        _snapshot(
            candidates=(
                _candidate("promotion-2", question="Same alias?"),
                _candidate("promotion-1", question=" SAME ALIAS!!! "),
            )
        )
    )
    assert tuple(item.promotion_id for item in decision.applicable_candidates) == (
        "promotion-1",
    )
    assert tuple(item.promotion_id for item in decision.skipped_candidates) == (
        "promotion-2",
    )


def test_alias_limit_allows_twelve_active_aliases() -> None:
    current = tuple(f"Alias {index}?" for index in range(11))
    decision = _policy().decide(_snapshot(possible_questions=current))
    assert len(decision.new_possible_questions) == 12


def test_thirteenth_active_alias_is_rejected() -> None:
    current = tuple(f"Alias {index}?" for index in range(12))
    with pytest.raises(
        WorkbenchRagEvalPromotionApplicationPolicyConflictError
    ) as exc_info:
        _policy().decide(_snapshot(possible_questions=current))
    assert exc_info.value.code is (
        WorkbenchRagEvalPromotionApplicationConflictCode.ALIAS_LIMIT_EXCEEDED
    )


def test_active_revision_conflicts_before_embedding_generation() -> None:
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
