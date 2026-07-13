from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalPromotionApplicationCandidate,
    WorkbenchRagEvalPromotionApplicationSnapshot,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_normalization_policy import (
    normalize_workbench_rag_eval_question,
)


class WorkbenchRagEvalPromotionApplicationDecisionCode(StrEnum):
    APPLY = "apply"
    NO_NEW_ALIASES = "no_new_aliases"
    EXISTING_ALIAS = "existing_alias"
    DUPLICATE_SELECTED_ALIAS = "duplicate_selected_alias"


class WorkbenchRagEvalPromotionApplicationConflictCode(StrEnum):
    NON_APPROVED_CANDIDATE = "non_approved_candidate"
    SUPERSEDED_CANDIDATE = "superseded_candidate"
    INACTIVE_TARGET = "inactive_target"
    UNPUBLISHED_TARGET = "unpublished_target"
    ACTIVE_REVISION = "active_revision"
    ALIAS_LIMIT_EXCEEDED = "alias_limit_exceeded"
    MIXED_SOURCE_RUNS = "mixed_source_runs"
    TARGET_FACT_MISMATCH = "target_fact_mismatch"
    DUPLICATE_PROMOTION_ID = "duplicate_promotion_id"


class WorkbenchRagEvalPromotionApplicationPolicyConflictError(ValueError):
    def __init__(
        self,
        *,
        code: WorkbenchRagEvalPromotionApplicationConflictCode,
        message: str,
        promotion_ids: tuple[str, ...],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.promotion_ids = promotion_ids


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationPolicyConfig:
    max_active_promoted_questions_per_runtime_entry: int = 12

    def __post_init__(self) -> None:
        value = self.max_active_promoted_questions_per_runtime_entry
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                "max_active_promoted_questions_per_runtime_entry must be > 0"
            )


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationSkippedCandidate:
    promotion_id: str
    code: WorkbenchRagEvalPromotionApplicationDecisionCode
    message: str


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationDecision:
    code: WorkbenchRagEvalPromotionApplicationDecisionCode
    applicable_candidates: tuple[
        WorkbenchRagEvalPromotionApplicationCandidate,
        ...,
    ]
    skipped_candidates: tuple[
        WorkbenchRagEvalPromotionApplicationSkippedCandidate,
        ...,
    ]
    new_possible_questions: tuple[str, ...]

    @property
    def should_apply(self) -> bool:
        return bool(self.applicable_candidates)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPromotionApplicationPolicy:
    config: WorkbenchRagEvalPromotionApplicationPolicyConfig = (
        WorkbenchRagEvalPromotionApplicationPolicyConfig()
    )

    def decide(
        self,
        snapshot: WorkbenchRagEvalPromotionApplicationSnapshot,
    ) -> WorkbenchRagEvalPromotionApplicationDecision:
        promotion_ids = tuple(
            candidate.promotion_id for candidate in snapshot.candidates
        )
        if len(set(promotion_ids)) != len(promotion_ids):
            raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                code=(
                    WorkbenchRagEvalPromotionApplicationConflictCode.DUPLICATE_PROMOTION_ID
                ),
                message="promotion application group contains duplicate promotion ids",
                promotion_ids=promotion_ids,
            )
        if snapshot.runtime_status != "active":
            raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                code=WorkbenchRagEvalPromotionApplicationConflictCode.INACTIVE_TARGET,
                message=(f"runtime entry {snapshot.runtime_entry_id} is not active"),
                promotion_ids=promotion_ids,
            )
        if snapshot.runtime_visibility != "published":
            raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                code=WorkbenchRagEvalPromotionApplicationConflictCode.UNPUBLISHED_TARGET,
                message=(f"runtime entry {snapshot.runtime_entry_id} is not published"),
                promotion_ids=promotion_ids,
            )
        if snapshot.active_revision_id is not None:
            raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                code=WorkbenchRagEvalPromotionApplicationConflictCode.ACTIVE_REVISION,
                message=(
                    "active PENDING_VERIFICATION revision already exists for "
                    f"{snapshot.runtime_entry_id}"
                ),
                promotion_ids=promotion_ids,
            )

        run_ids = {candidate.run_id for candidate in snapshot.candidates}
        if len(run_ids) != 1:
            raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                code=WorkbenchRagEvalPromotionApplicationConflictCode.MIXED_SOURCE_RUNS,
                message=(
                    "promotion application group must belong to one source RAG Eval run"
                ),
                promotion_ids=promotion_ids,
            )

        for candidate in snapshot.candidates:
            if candidate.target_fact_id != snapshot.fact_id:
                raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                    code=(
                        WorkbenchRagEvalPromotionApplicationConflictCode.TARGET_FACT_MISMATCH
                    ),
                    message=(f"promotion {candidate.promotion_id} target fact changed"),
                    promotion_ids=(candidate.promotion_id,),
                )
            if candidate.status is WorkbenchRagEvalPromotionStatus.SUPERSEDED:
                raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                    code=(
                        WorkbenchRagEvalPromotionApplicationConflictCode.SUPERSEDED_CANDIDATE
                    ),
                    message=(f"promotion {candidate.promotion_id} is superseded"),
                    promotion_ids=(candidate.promotion_id,),
                )
            if candidate.status is not WorkbenchRagEvalPromotionStatus.APPROVED:
                raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                    code=(
                        WorkbenchRagEvalPromotionApplicationConflictCode.NON_APPROVED_CANDIDATE
                    ),
                    message=(
                        f"promotion {candidate.promotion_id} cannot apply status "
                        f"{candidate.status.value}"
                    ),
                    promotion_ids=(candidate.promotion_id,),
                )

        existing_by_normalized = {
            normalize_workbench_rag_eval_question(question): question
            for question in snapshot.possible_questions
        }
        selected_normalized: set[str] = set()
        applicable: list[WorkbenchRagEvalPromotionApplicationCandidate] = []
        skipped: list[WorkbenchRagEvalPromotionApplicationSkippedCandidate] = []

        for candidate in sorted(
            snapshot.candidates,
            key=lambda item: item.promotion_id,
        ):
            normalized = normalize_workbench_rag_eval_question(candidate.question)
            if not normalized:
                raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                    code=(
                        WorkbenchRagEvalPromotionApplicationConflictCode.NON_APPROVED_CANDIDATE
                    ),
                    message=(
                        f"promotion {candidate.promotion_id} question normalizes to empty"
                    ),
                    promotion_ids=(candidate.promotion_id,),
                )
            if normalized in existing_by_normalized:
                skipped.append(
                    WorkbenchRagEvalPromotionApplicationSkippedCandidate(
                        promotion_id=candidate.promotion_id,
                        code=(
                            WorkbenchRagEvalPromotionApplicationDecisionCode.EXISTING_ALIAS
                        ),
                        message=(
                            f"promotion {candidate.promotion_id} question already exists"
                        ),
                    )
                )
                continue
            if normalized in selected_normalized:
                skipped.append(
                    WorkbenchRagEvalPromotionApplicationSkippedCandidate(
                        promotion_id=candidate.promotion_id,
                        code=(
                            WorkbenchRagEvalPromotionApplicationDecisionCode.DUPLICATE_SELECTED_ALIAS
                        ),
                        message=(
                            f"promotion {candidate.promotion_id} duplicates another "
                            "selected alias"
                        ),
                    )
                )
                continue
            selected_normalized.add(normalized)
            applicable.append(candidate)

        new_possible_questions = (
            *snapshot.possible_questions,
            *(candidate.question.strip() for candidate in applicable),
        )
        limit = self.config.max_active_promoted_questions_per_runtime_entry
        if len(new_possible_questions) > limit:
            raise WorkbenchRagEvalPromotionApplicationPolicyConflictError(
                code=(
                    WorkbenchRagEvalPromotionApplicationConflictCode.ALIAS_LIMIT_EXCEEDED
                ),
                message=(
                    f"runtime entry {snapshot.runtime_entry_id} would have "
                    f"{len(new_possible_questions)} active promoted aliases; limit is "
                    f"{limit}"
                ),
                promotion_ids=tuple(candidate.promotion_id for candidate in applicable),
            )

        code = (
            WorkbenchRagEvalPromotionApplicationDecisionCode.APPLY
            if applicable
            else WorkbenchRagEvalPromotionApplicationDecisionCode.NO_NEW_ALIASES
        )
        return WorkbenchRagEvalPromotionApplicationDecision(
            code=code,
            applicable_candidates=tuple(applicable),
            skipped_candidates=tuple(skipped),
            new_possible_questions=tuple(new_possible_questions),
        )
