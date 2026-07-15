from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
)
from src.contexts.llm_runtime.application.capacity.llm_capacity_estimate_payload import (
    build_llm_capacity_estimate_payload,
)
from src.contexts.llm_runtime.domain.entities.model_profile import (
    ModelProfile,
)


ADJUDICATION_PROMPT_VERSION = "workbench_rag_eval_question_adjudication.ru.v1"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationEligibilityPolicy:
    pass_weak_enabled: bool = True

    def eligible_classifications(
        self,
    ) -> frozenset[WorkbenchRagEvalRetrievalClassification]:
        values = {
            WorkbenchRagEvalRetrievalClassification.MISS,
            WorkbenchRagEvalRetrievalClassification.CONFUSION,
        }
        if self.pass_weak_enabled:
            values.add(WorkbenchRagEvalRetrievalClassification.PASS_WEAK)
        return frozenset(values)

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
            and classification in self.eligible_classifications()
        )


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot:
    rank: int
    runtime_entry_id: str
    fact_id: str
    claim: str
    score: float

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "runtime_entry_id": self.runtime_entry_id,
            "fact_id": self.fact_id,
            "claim": self.claim,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationPlanningInput:
    run_id: str
    project_id: str
    question_id: str
    question: str
    evaluation_role: WorkbenchRagEvalQuestionRole
    promotion_eligible: bool
    ambiguity_risk: WorkbenchRagEvalQuestionAmbiguityRisk | None
    outcome_id: str
    classification: WorkbenchRagEvalRetrievalClassification
    expected_runtime_entry_id: str
    expected_fact_id: str
    expected_rank: int | None
    expected_score: float | None
    best_competitor_runtime_entry_id: str | None
    best_competitor_fact_id: str | None
    best_competitor_score: float | None
    score_margin: float | None
    target_claim: str
    target_possible_questions: tuple[str, ...]
    target_exclusion_scope: str | None
    target_evidence_block: str
    retrieved: tuple[WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot, ...]


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationWorkPlanner:
    adjudication_model_profile: ModelProfile
    prompt_version: str = ADJUDICATION_PROMPT_VERSION
    planned_output_tokens: int = 700
    eligibility_policy: WorkbenchRagEvalAdjudicationEligibilityPolicy = (
        WorkbenchRagEvalAdjudicationEligibilityPolicy()
    )

    def plan(
        self,
        *,
        inputs: tuple[WorkbenchRagEvalAdjudicationPlanningInput, ...],
        provider_messages_by_question_id: Mapping[
            str,
            tuple[Mapping[str, str], ...],
        ],
    ) -> tuple[WorkItemSchedulePlan, ...]:
        model_profile = self._adjudication_model_profile()
        return tuple(
            self._plan_one(
                item,
                provider_messages_by_question_id[item.question_id],
                model_profile,
            )
            for item in inputs
            if self.eligibility_policy.is_eligible(
                evaluation_role=item.evaluation_role,
                promotion_eligible=item.promotion_eligible,
                ambiguity_risk=item.ambiguity_risk,
                classification=item.classification,
            )
        )

    def _plan_one(
        self,
        item: WorkbenchRagEvalAdjudicationPlanningInput,
        provider_messages: tuple[Mapping[str, str], ...],
        model_profile: ModelProfile,
    ) -> WorkItemSchedulePlan:
        work_item_id = _stable_id(
            item.run_id,
            item.question_id,
            item.outcome_id,
            self.prompt_version,
            "adjudication",
        )
        prompt_payload = _prompt_payload(item)
        payload = {
            "workflow_run_id": item.run_id,
            "project_id": item.project_id,
            "question_id": item.question_id,
            "outcome_id": item.outcome_id,
            "prompt_version": self.prompt_version,
            "operation": "adjudication",
            "question": item.question,
            "expected_runtime_entry_id": item.expected_runtime_entry_id,
            "expected_fact_id": item.expected_fact_id,
            "classification": item.classification.value,
            "expected_rank": item.expected_rank,
            "expected_score": item.expected_score,
            "best_competitor_runtime_entry_id": item.best_competitor_runtime_entry_id,
            "best_competitor_fact_id": item.best_competitor_fact_id,
            "best_competitor_score": item.best_competitor_score,
            "score_margin": item.score_margin,
            "target": prompt_payload["target"],
            "retrieval_outcome": prompt_payload["retrieval_outcome"],
            "retrieved": prompt_payload["retrieved"],
            "provider_messages": [dict(message) for message in provider_messages],
            "llm_capacity_estimate": _capacity_estimate(
                provider_messages=provider_messages,
                planned_output_tokens=self.planned_output_tokens,
                model_profile=model_profile,
            ),
        }
        return WorkItemSchedulePlan(
            work_item_id=work_item_id,
            work_kind=WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
            idempotency_key=work_item_id,
            payload=payload,
        )

    def _adjudication_model_profile(self) -> ModelProfile:
        if not isinstance(self.adjudication_model_profile, ModelProfile):
            raise TypeError("adjudication_model_profile must be ModelProfile")
        return self.adjudication_model_profile


def build_adjudication_prompt_payload(
    item: WorkbenchRagEvalAdjudicationPlanningInput,
) -> dict[str, object]:
    return _prompt_payload(item)


def _prompt_payload(
    item: WorkbenchRagEvalAdjudicationPlanningInput,
) -> dict[str, object]:
    return {
        "question": item.question,
        "target": {
            "runtime_entry_id": item.expected_runtime_entry_id,
            "fact_id": item.expected_fact_id,
            "claim": item.target_claim,
            "possible_questions": list(item.target_possible_questions),
            "exclusion_scope": item.target_exclusion_scope,
            "evidence_block": item.target_evidence_block,
        },
        "retrieval_outcome": {
            "classification": item.classification.value,
            "expected_rank": item.expected_rank,
            "expected_score": item.expected_score,
            "score_margin": item.score_margin,
        },
        "retrieved": [snapshot.to_prompt_dict() for snapshot in item.retrieved],
    }


def build_adjudication_provider_messages(
    *,
    prompt_template: str,
    item: WorkbenchRagEvalAdjudicationPlanningInput,
) -> tuple[Mapping[str, str], ...]:
    return (
        {"role": "system", "content": prompt_template},
        {
            "role": "user",
            "content": json.dumps(
                build_adjudication_prompt_payload(item),
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    )


def _capacity_estimate(
    *,
    provider_messages: tuple[Mapping[str, str], ...],
    planned_output_tokens: int,
    model_profile: ModelProfile,
) -> dict[str, object]:
    prompt_text = "\n".join(
        str(message.get("content", "")) for message in provider_messages
    )
    input_tokens = max(1, len(prompt_text) // 4)
    return build_llm_capacity_estimate_payload(
        model_profile=model_profile,
        phase="adjudication",
        operation="prepare_workbench_rag_eval_adjudication",
        estimator="provider_message_char_div_4",
        prompt_tokens=input_tokens,
        artifact_tokens=0,
        input_tokens=input_tokens,
        planned_output_tokens=planned_output_tokens,
        safety_gap_tokens=0,
    )


def _stable_id(*parts: str) -> str:
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
