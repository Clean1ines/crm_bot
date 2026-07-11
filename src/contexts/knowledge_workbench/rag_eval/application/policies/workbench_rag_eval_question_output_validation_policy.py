from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)


class WorkbenchRagEvalQuestionOutputValidationOutcome(StrEnum):
    VALID_QUESTION_SET = "VALID_QUESTION_SET"
    INVALID_JSON = "INVALID_JSON"
    INVALID_CONTRACT_VERSION = "INVALID_CONTRACT_VERSION"
    INVALID_ROOT = "INVALID_ROOT"
    INVALID_QUESTION_COUNT = "INVALID_QUESTION_COUNT"
    INVALID_KIND_DISTRIBUTION = "INVALID_KIND_DISTRIBUTION"
    INVALID_ITEM = "INVALID_ITEM"
    DUPLICATE_GENERATED_QUESTION = "DUPLICATE_GENERATED_QUESTION"
    DUPLICATE_EXISTING_QUESTION = "DUPLICATE_EXISTING_QUESTION"
    INVALID_PROMOTION_ELIGIBILITY = "INVALID_PROMOTION_ELIGIBILITY"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionOutputValidationResult:
    outcome: WorkbenchRagEvalQuestionOutputValidationOutcome
    questions: tuple[GeneratedWorkbenchRagEvalQuestion, ...]
    error: str | None


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionOutputValidationPolicy:
    question_generator: WorkbenchRagEvalQuestionGenerator

    def validate(
        self,
        *,
        raw_text: str,
        existing_possible_questions: tuple[str, ...],
    ) -> WorkbenchRagEvalQuestionOutputValidationResult:
        try:
            questions = self.question_generator.parse_questions_from_raw_text(
                raw_text=raw_text,
                generation_model="validation/model",
                generation_account_ref="validation-account",
                generation_slot_index=0,
                existing_possible_questions=existing_possible_questions,
            )
        except WorkbenchRagEvalQuestionGenerationError as exc:
            outcome = _outcome_from_error_message(str(exc))
            return WorkbenchRagEvalQuestionOutputValidationResult(
                outcome=outcome,
                questions=(),
                error=str(exc),
            )
        return WorkbenchRagEvalQuestionOutputValidationResult(
            WorkbenchRagEvalQuestionOutputValidationOutcome.VALID_QUESTION_SET,
            questions,
            None,
        )


def _outcome_from_error_message(
    message: str,
) -> WorkbenchRagEvalQuestionOutputValidationOutcome:
    prefix = message.split(":", 1)[0].strip()
    try:
        return WorkbenchRagEvalQuestionOutputValidationOutcome(prefix)
    except ValueError:
        return WorkbenchRagEvalQuestionOutputValidationOutcome.INVALID_ITEM
