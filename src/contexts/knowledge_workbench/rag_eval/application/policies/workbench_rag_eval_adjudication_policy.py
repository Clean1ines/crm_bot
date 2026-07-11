from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalAdjudicationVerdict,
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalPassWeakAdjudicationEligibilityConfig:
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationEligibilityPolicy:
    pass_weak: WorkbenchRagEvalPassWeakAdjudicationEligibilityConfig

    @classmethod
    def default(cls) -> "WorkbenchRagEvalAdjudicationEligibilityPolicy":
        return cls(pass_weak=WorkbenchRagEvalPassWeakAdjudicationEligibilityConfig())

    @property
    def eligible_classifications(
        self,
    ) -> tuple[WorkbenchRagEvalRetrievalClassification, ...]:
        values = [
            WorkbenchRagEvalRetrievalClassification.MISS,
            WorkbenchRagEvalRetrievalClassification.CONFUSION,
        ]
        if self.pass_weak.enabled:
            values.append(WorkbenchRagEvalRetrievalClassification.PASS_WEAK)
        return tuple(values)

    def is_eligible(
        self,
        *,
        evaluation_role: WorkbenchRagEvalQuestionRole,
        promotion_eligible: bool,
        ambiguity_risk: WorkbenchRagEvalQuestionAmbiguityRisk | None,
        classification: WorkbenchRagEvalRetrievalClassification,
    ) -> bool:
        return (
            evaluation_role is WorkbenchRagEvalQuestionRole.PROMOTION_POOL
            and promotion_eligible
            and ambiguity_risk is WorkbenchRagEvalQuestionAmbiguityRisk.LOW
            and classification in self.eligible_classifications
        )


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationPromotionCandidatePolicy:
    eligibility_policy: WorkbenchRagEvalAdjudicationEligibilityPolicy

    @classmethod
    def default(cls) -> "WorkbenchRagEvalAdjudicationPromotionCandidatePolicy":
        return cls(
            eligibility_policy=WorkbenchRagEvalAdjudicationEligibilityPolicy.default()
        )

    def should_create_candidate(
        self,
        *,
        evaluation_role: WorkbenchRagEvalQuestionRole,
        promotion_eligible: bool,
        ambiguity_risk: WorkbenchRagEvalQuestionAmbiguityRisk | None,
        classification: WorkbenchRagEvalRetrievalClassification,
        verdict: WorkbenchRagEvalAdjudicationVerdict,
        promotion_recommended: bool,
    ) -> bool:
        return (
            self.eligibility_policy.is_eligible(
                evaluation_role=evaluation_role,
                promotion_eligible=promotion_eligible,
                ambiguity_risk=ambiguity_risk,
                classification=classification,
            )
            and verdict is WorkbenchRagEvalAdjudicationVerdict.VALID_TARGET_QUERY
            and promotion_recommended
        )


__all__ = [
    "WorkbenchRagEvalAdjudicationEligibilityPolicy",
    "WorkbenchRagEvalAdjudicationPromotionCandidatePolicy",
    "WorkbenchRagEvalAdjudicationVerdict",
    "WorkbenchRagEvalPassWeakAdjudicationEligibilityConfig",
]
