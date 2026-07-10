from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_attempt_decision_policy import (
    WorkbenchRagEvalQuestionAttemptDecision,
    WorkbenchRagEvalQuestionAttemptDecisionKind,
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionAttemptNextAction:
    retry_plan: WorkItemRetryPlan
    reason: str
    terminal: bool


class WorkbenchRagEvalQuestionAttemptNextActionPolicy:
    def decide_next_action(
        self, decision: WorkbenchRagEvalQuestionAttemptDecision
    ) -> WorkbenchRagEvalQuestionAttemptNextAction:
        plans = {
            WorkbenchRagEvalQuestionAttemptDecisionKind.RETRY_SAME_ROUTE: WorkItemRetryPlan.RETRY_SAME_ROUTE,
            WorkbenchRagEvalQuestionAttemptDecisionKind.RETRY_FALLBACK_ROUTE: WorkItemRetryPlan.RETRY_DAILY_FALLBACK_ROUTE,
            WorkbenchRagEvalQuestionAttemptDecisionKind.WAIT_CAPACITY_WINDOW: WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW,
            WorkbenchRagEvalQuestionAttemptDecisionKind.RETRY_LARGER_INPUT_ROUTE: WorkItemRetryPlan.RETRY_LARGER_INPUT_LIMIT_ROUTE,
            WorkbenchRagEvalQuestionAttemptDecisionKind.TERMINAL: WorkItemRetryPlan.TERMINAL,
        }
        return WorkbenchRagEvalQuestionAttemptNextAction(
            retry_plan=plans[decision.kind],
            reason=decision.reason,
            terminal=decision.kind
            is WorkbenchRagEvalQuestionAttemptDecisionKind.TERMINAL,
        )
