from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol, cast

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalAdjudication,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_adjudication_output_validation_policy import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION,
    WorkbenchRagEvalAdjudicationOutputValidationOutcome,
    WorkbenchRagEvalAdjudicationOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
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
class WorkbenchRagEvalAdjudicationOutputValidator:
    def validate(
        self,
        *,
        dispatch_payload: Mapping[str, object],
        output_payload: Mapping[str, object] | None,
        llm_status: LlmDispatchExecutionStatus,
        finished_at: datetime,
        attempt_number: int,
    ) -> LlmDispatchOutputValidationResult:
        del dispatch_payload, finished_at, attempt_number
        if llm_status is not LlmDispatchExecutionStatus.SUCCEEDED:
            return LlmDispatchOutputValidationResult(
                status=llm_status,
                error_kind=None,
                next_attempt_at=None,
                metadata={
                    "validation_decision": None,
                    "validation_error": None,
                },
            )
        raw_text = (
            output_payload.get("raw_text") if output_payload is not None else None
        )
        validation = WorkbenchRagEvalAdjudicationOutputValidationPolicy().validate(
            raw_text=raw_text if isinstance(raw_text, str) else "",
        )
        if (
            validation.outcome
            is not WorkbenchRagEvalAdjudicationOutputValidationOutcome.VALID_ADJUDICATION
        ):
            return LlmDispatchOutputValidationResult(
                status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
                error_kind=_error_kind(validation.outcome),
                next_attempt_at=None,
                metadata={
                    "validation_decision": validation.outcome.value,
                    "validation_error": validation.error or validation.outcome.value,
                },
            )
        return LlmDispatchOutputValidationResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            error_kind=None,
            next_attempt_at=None,
            metadata={
                "validation_decision": validation.outcome.value,
                "validation_error": None,
            },
        )


@dataclass(frozen=True, slots=True)
class ExecuteWorkbenchRagEvalAdjudicationCommand:
    dispatch_attempt_id: str


@dataclass(frozen=True, slots=True)
class ExecuteWorkbenchRagEvalAdjudicationResult:
    dispatch_attempt_id: str
    work_item_id: str
    saved_adjudication_count: int
    outcome_status: str
    finished_at: datetime
    capacity_observation: Mapping[str, object] | None
    error_kind: str | None
    next_attempt_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExecuteWorkbenchRagEvalAdjudication:
    execute_prepared_llm_dispatch_attempt: ExecutePreparedLlmDispatchAttemptPort
    rag_eval_repository: WorkbenchRagEvalRepositoryPort

    async def execute(
        self,
        command: ExecuteWorkbenchRagEvalAdjudicationCommand,
    ) -> ExecuteWorkbenchRagEvalAdjudicationResult:
        execution_result = cast(
            ExecutePreparedLlmDispatchAttemptResult,
            await self.execute_prepared_llm_dispatch_attempt.execute(
                ExecutePreparedLlmDispatchAttemptCommand(
                    attempt_id=command.dispatch_attempt_id,
                    output_validator=WorkbenchRagEvalAdjudicationOutputValidator(),
                )
            ),
        )
        if (
            execution_result.llm_result.status
            is not LlmDispatchExecutionStatus.SUCCEEDED
        ):
            return ExecuteWorkbenchRagEvalAdjudicationResult(
                dispatch_attempt_id=command.dispatch_attempt_id,
                work_item_id=execution_result.dispatch.work_item_id,
                saved_adjudication_count=0,
                outcome_status=execution_result.llm_result.status.value,
                finished_at=execution_result.llm_result.finished_at,
                capacity_observation=execution_result.llm_result.capacity_observation,
                error_kind=execution_result.llm_result.error_kind,
                next_attempt_at=execution_result.llm_result.next_attempt_at,
            )
        adjudication = _adjudication_from_execution_result(execution_result)
        await self.rag_eval_repository.save_question_adjudication(
            adjudication=adjudication
        )
        return ExecuteWorkbenchRagEvalAdjudicationResult(
            dispatch_attempt_id=command.dispatch_attempt_id,
            work_item_id=execution_result.dispatch.work_item_id,
            saved_adjudication_count=1,
            outcome_status=execution_result.llm_result.status.value,
            finished_at=execution_result.llm_result.finished_at,
            capacity_observation=execution_result.llm_result.capacity_observation,
            error_kind=execution_result.llm_result.error_kind,
            next_attempt_at=execution_result.llm_result.next_attempt_at,
        )


def _adjudication_from_execution_result(
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
) -> WorkbenchRagEvalAdjudication:
    dispatch = execution_result.dispatch
    schedule_payload = _mapping(dispatch.dispatch_payload, "schedule_payload")
    allocation = _mapping(dispatch.dispatch_payload, "llm_allocation")
    validation = WorkbenchRagEvalAdjudicationOutputValidationPolicy().validate(
        raw_text=_raw_output_text(execution_result.llm_result.output_payload),
    )
    if validation.adjudication is None:
        raise ValueError("successful adjudication execution requires valid output")
    run_id = _text(schedule_payload, "workflow_run_id")
    question_id = _text(schedule_payload, "question_id")
    outcome_id = _text(schedule_payload, "outcome_id")
    expected_runtime_entry_id = _text(schedule_payload, "expected_runtime_entry_id")
    expected_fact_id = _text(schedule_payload, "expected_fact_id")
    return WorkbenchRagEvalAdjudication(
        adjudication_id=_stable_id(
            "adjudication",
            run_id,
            question_id,
            outcome_id,
        ),
        run_id=run_id,
        project_id=_text(schedule_payload, "project_id"),
        question_id=question_id,
        outcome_id=outcome_id,
        expected_runtime_entry_id=expected_runtime_entry_id,
        expected_fact_id=expected_fact_id,
        verdict=validation.adjudication.verdict,
        promotion_recommended=validation.adjudication.promotion_recommended,
        reason=validation.adjudication.reason,
        contract_version=WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION,
        model_ref=_text(allocation, "model_ref"),
        account_ref=_text(allocation, "account_ref"),
        slot_index=_int(allocation, "slot_index"),
        attempt_id=dispatch.attempt_id,
        created_at=execution_result.llm_result.finished_at,
        updated_at=execution_result.llm_result.finished_at,
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
    return value.strip()


def _int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be int")
    return value


def _stable_id(*parts: str) -> str:
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _error_kind(outcome: WorkbenchRagEvalAdjudicationOutputValidationOutcome) -> str:
    if outcome is WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_JSON:
        return "invalid_json"
    return "invalid_contract"
