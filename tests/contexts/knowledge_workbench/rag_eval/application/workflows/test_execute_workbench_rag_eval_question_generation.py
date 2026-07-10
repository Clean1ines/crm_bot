from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
)
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcomeResult,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestion,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_question_generation import (
    ExecuteWorkbenchRagEvalQuestionGeneration,
    ExecuteWorkbenchRagEvalQuestionGenerationCommand,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)


def _now() -> datetime:
    return datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


def _raw_questions() -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "question": f"Как спросить про факт {index}?",
                    "question_kind": "paraphrase",
                }
                for index in range(10)
            ]
        },
        ensure_ascii=False,
    )


@dataclass(slots=True)
class FakeExecutePreparedDispatch:
    received: list[ExecutePreparedLlmDispatchAttemptCommand] = field(
        default_factory=list
    )

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> ExecutePreparedLlmDispatchAttemptResult:
        self.received.append(command)
        dispatch = WorkItemAttemptDispatchForExecution(
            attempt_id=command.attempt_id,
            work_item_id="work-1",
            attempt_number=1,
            lease_token=LeaseToken("lease-1"),
            worker_ref="worker-1",
            dispatch_payload={
                "schedule_payload": {
                    "workflow_run_id": "run-1",
                    "project_id": "project-1",
                    "runtime_entry_id": "runtime-entry-1",
                    "expected_fact_id": "fact-1",
                    "prompt_version": "prompt-v1",
                },
                "llm_allocation": {
                    "provider": "groq",
                    "account_ref": "groq_org_secondary",
                    "model_ref": "qwen/qwen3-32b",
                    "slot_index": 1,
                },
            },
            started_at=_now(),
        )
        provider_result = LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_now(),
            output_payload={"raw_text": _raw_questions()},
        )
        validation_result = command.output_validator.validate(
            dispatch_payload=dispatch.dispatch_payload,
            output_payload=provider_result.output_payload,
            llm_status=provider_result.status,
            finished_at=provider_result.finished_at,
            attempt_number=dispatch.attempt_number,
        )
        assert validation_result.status is LlmDispatchExecutionStatus.SUCCEEDED
        assert validation_result.metadata["validated_question_count"] == 10
        return ExecutePreparedLlmDispatchAttemptResult(
            dispatch=dispatch,
            llm_result=provider_result,
            outcome_result=RecordWorkItemAttemptOutcomeResult(
                work_item=WorkItem(
                    work_item_id=dispatch.work_item_id,
                    work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
                )
            ),
            validation_metadata=validation_result.metadata,
        )


@dataclass(slots=True)
class FakeRagEvalRepository:
    saved_questions: list[WorkbenchRagEvalQuestion] = field(default_factory=list)

    async def save_generated_questions(
        self,
        *,
        questions: tuple[WorkbenchRagEvalQuestion, ...],
    ) -> tuple[WorkbenchRagEvalQuestion, ...]:
        self.saved_questions.extend(questions)
        return questions


async def test_execute_qgen_uses_prepared_dispatch_and_persists_ten_questions() -> None:
    executor = FakeExecutePreparedDispatch()
    repository = FakeRagEvalRepository()

    result = await ExecuteWorkbenchRagEvalQuestionGeneration(
        execute_prepared_llm_dispatch_attempt=executor,
        rag_eval_repository=repository,
        question_generator=WorkbenchRagEvalQuestionGenerator.from_prompt_file(),
    ).execute(
        ExecuteWorkbenchRagEvalQuestionGenerationCommand(
            dispatch_attempt_id="attempt-1",
        )
    )

    assert result.saved_question_count == 10
    assert len(repository.saved_questions) == 10
    assert executor.received[0].attempt_id == "attempt-1"
    assert executor.received[0].output_validator is not None
    assert {question.generation_model for question in repository.saved_questions} == {
        "qwen/qwen3-32b"
    }
    assert {
        question.generation_account_ref for question in repository.saved_questions
    } == {"groq_org_secondary"}
    assert {
        question.generation_slot_index for question in repository.saved_questions
    } == {1}
