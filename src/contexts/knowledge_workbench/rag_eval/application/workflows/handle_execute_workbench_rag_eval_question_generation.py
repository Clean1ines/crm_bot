from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol, cast

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionStatus,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
    LlmDispatchOutputValidationResult,
)


class ExecutePreparedLlmDispatchAttemptPort(Protocol):
    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerationOutputValidator:
    question_generator: WorkbenchRagEvalQuestionGenerator

    def validate(
        self,
        *,
        dispatch_payload: Mapping[str, object],
        output_payload: Mapping[str, object] | None,
        llm_status: LlmDispatchExecutionStatus,
        finished_at: datetime,
        attempt_number: int,
    ) -> LlmDispatchOutputValidationResult:
        del finished_at, attempt_number
        if llm_status is not LlmDispatchExecutionStatus.SUCCEEDED:
            return LlmDispatchOutputValidationResult(
                status=llm_status,
                error_kind=None,
                next_attempt_at=None,
                metadata={"validated_question_count": 0},
            )
        try:
            raw_text = _raw_output_text(output_payload)
            schedule_payload = _mapping(dispatch_payload, "schedule_payload")
            questions = self.question_generator.parse_questions_from_raw_text(
                raw_text=raw_text,
                generation_model="validation/model",
                generation_account_ref="validation-account",
                generation_slot_index=0,
                existing_possible_questions=_string_tuple(
                    schedule_payload,
                    "possible_questions",
                ),
            )
        except Exception as exc:
            return LlmDispatchOutputValidationResult(
                status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
                error_kind="workbench_rag_eval_question_generation_validation_failed",
                next_attempt_at=None,
                metadata={
                    "validated_question_count": 0,
                    "validation_error": str(exc),
                },
            )
        return LlmDispatchOutputValidationResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            error_kind=None,
            next_attempt_at=None,
            metadata={"validated_question_count": len(questions)},
        )


@dataclass(frozen=True, slots=True)
class ExecuteWorkbenchRagEvalQuestionGenerationCommand:
    dispatch_attempt_id: str


@dataclass(frozen=True, slots=True)
class ExecuteWorkbenchRagEvalQuestionGenerationResult:
    dispatch_attempt_id: str
    work_item_id: str
    saved_question_count: int
    outcome_status: str


@dataclass(frozen=True, slots=True)
class ExecuteWorkbenchRagEvalQuestionGeneration:
    execute_prepared_llm_dispatch_attempt: ExecutePreparedLlmDispatchAttemptPort
    rag_eval_repository: WorkbenchRagEvalRepositoryPort
    question_generator: WorkbenchRagEvalQuestionGenerator

    async def execute(
        self,
        command: ExecuteWorkbenchRagEvalQuestionGenerationCommand,
    ) -> ExecuteWorkbenchRagEvalQuestionGenerationResult:
        execution_result = cast(
            ExecutePreparedLlmDispatchAttemptResult,
            await self.execute_prepared_llm_dispatch_attempt.execute(
                ExecutePreparedLlmDispatchAttemptCommand(
                    attempt_id=command.dispatch_attempt_id,
                    output_validator=WorkbenchRagEvalQuestionGenerationOutputValidator(
                        question_generator=self.question_generator,
                    ),
                )
            ),
        )
        if (
            execution_result.llm_result.status
            is not LlmDispatchExecutionStatus.SUCCEEDED
        ):
            return ExecuteWorkbenchRagEvalQuestionGenerationResult(
                dispatch_attempt_id=command.dispatch_attempt_id,
                work_item_id=execution_result.dispatch.work_item_id,
                saved_question_count=0,
                outcome_status=execution_result.llm_result.status.value,
            )

        questions = _questions_from_execution_result(
            execution_result=execution_result,
            question_generator=self.question_generator,
        )
        await self.rag_eval_repository.save_generated_questions(questions=questions)
        return ExecuteWorkbenchRagEvalQuestionGenerationResult(
            dispatch_attempt_id=command.dispatch_attempt_id,
            work_item_id=execution_result.dispatch.work_item_id,
            saved_question_count=len(questions),
            outcome_status=execution_result.llm_result.status.value,
        )


def _questions_from_execution_result(
    *,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    question_generator: WorkbenchRagEvalQuestionGenerator,
) -> tuple[WorkbenchRagEvalQuestion, ...]:
    dispatch = execution_result.dispatch
    schedule_payload = _mapping(dispatch.dispatch_payload, "schedule_payload")
    allocation = _mapping(dispatch.dispatch_payload, "llm_allocation")
    workflow_run_id = _text(schedule_payload, "workflow_run_id")
    project_id = _text(schedule_payload, "project_id")
    runtime_entry_id = _text(schedule_payload, "runtime_entry_id")
    expected_fact_id = _text(schedule_payload, "expected_fact_id")
    prompt_version = _text(schedule_payload, "prompt_version")
    model_ref = _text(allocation, "model_ref")
    account_ref = _text(allocation, "account_ref")
    slot_index = _int(allocation, "slot_index")
    generated = question_generator.parse_questions_from_raw_text(
        raw_text=_raw_output_text(execution_result.llm_result.output_payload),
        generation_model=model_ref,
        generation_account_ref=account_ref,
        generation_slot_index=slot_index,
        existing_possible_questions=_string_tuple(
            schedule_payload,
            "possible_questions",
        ),
    )
    return tuple(
        WorkbenchRagEvalQuestion(
            question_id=_stable_id(workflow_run_id, runtime_entry_id, item.question),
            run_id=workflow_run_id,
            project_id=project_id,
            expected_runtime_entry_id=runtime_entry_id,
            expected_fact_id=expected_fact_id,
            question=item.question,
            question_kind=item.question_kind,
            source=item.source,
            generation_model=item.generation_model,
            prompt_version=prompt_version,
            contract_version=item.contract_version,
            promotion_eligible=item.promotion_eligible,
            ambiguity_risk=item.ambiguity_risk,
            generation_rationale=item.generation_rationale,
            generation_account_ref=item.generation_account_ref,
            generation_slot_index=item.generation_slot_index,
            status=WorkbenchRagEvalQuestionStatus.CREATED,
            created_at=execution_result.llm_result.finished_at,
        )
        for item in generated
    )


def _raw_output_text(output_payload: Mapping[str, object] | None) -> str:
    if output_payload is None:
        raise ValueError("output_payload is required")
    raw_text = output_payload.get("raw_text")
    if not isinstance(raw_text, str):
        raise ValueError("output_payload.raw_text is required")
    return raw_text


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be object")
    return value


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty string")
    return value


def _int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be int")
    return value


def _string_tuple(
    payload: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{key} must be list or tuple")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key} must contain non-empty strings")
        result.append(item.strip())
    return tuple(result)


def _stable_id(*parts: str) -> str:
    return sha256(":".join(parts).encode("utf-8")).hexdigest()
