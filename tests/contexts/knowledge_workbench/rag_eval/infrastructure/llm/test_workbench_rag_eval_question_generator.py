from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

import pytest

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerationError,
    WorkbenchRagEvalQuestionGenerator,
)


@dataclass(slots=True)
class FakeLlmDispatchExecutor:
    raw_text: str
    last_input: LlmDispatchExecutionInput | None = None
    status: LlmDispatchExecutionStatus = LlmDispatchExecutionStatus.SUCCEEDED

    async def execute_dispatch(
        self,
        execution_input: LlmDispatchExecutionInput,
    ) -> LlmDispatchExecutionResult:
        self.last_input = execution_input
        if self.status is not LlmDispatchExecutionStatus.SUCCEEDED:
            return LlmDispatchExecutionResult(
                status=self.status,
                finished_at=datetime.now(timezone.utc),
                error_kind="test_error",
            )
        return LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=datetime.now(timezone.utc),
            output_payload={"raw_text": self.raw_text},
        )


@pytest.mark.asyncio
async def test_question_generator_parses_valid_json_and_uses_dispatch_boundary() -> (
    None
):
    executor = FakeLlmDispatchExecutor(
        raw_text=json.dumps(
            {
                "questions": [
                    {
                        "question": "Как спросит пользователь?",
                        "question_kind": "paraphrase",
                    },
                    {"question": "   ", "question_kind": "synonym"},
                    {
                        "question": "Как спросит пользователь?",
                        "question_kind": "synonym",
                    },
                    {
                        "question": "Простой вопрос?",
                        "question_kind": "naive_user_question",
                    },
                ]
            },
            ensure_ascii=False,
        )
    )
    generator = WorkbenchRagEvalQuestionGenerator(
        llm_dispatch_executor=executor,
        prompt_template="prompt without answer_text",
        max_questions_per_entry=20,
    )

    result = await generator.generate_questions_for_entry(
        claim="Claim text",
        possible_questions=("Existing?",),
        exclusion_scope="Not X",
        evidence_block="Evidence",
        triples=({"subject": "A", "predicate": "rel", "object": "B"},),
    )

    assert tuple(item.question for item in result) == (
        "Как спросит пользователь?",
        "Простой вопрос?",
    )
    assert tuple(item.question_kind.value for item in result) == (
        "paraphrase",
        "naive_user_question",
    )
    assert executor.last_input is not None
    payload = executor.last_input.dispatch_payload
    assert "schedule_payload" in payload
    assert "llm_allocation" in payload
    assert "llm_execution_settings" in payload


@pytest.mark.asyncio
async def test_question_generator_rejects_invalid_question_kind() -> None:
    generator = WorkbenchRagEvalQuestionGenerator(
        llm_dispatch_executor=FakeLlmDispatchExecutor(
            raw_text=json.dumps(
                {"questions": [{"question": "Q?", "question_kind": "answer"}]}
            )
        ),
        prompt_template="prompt",
    )

    with pytest.raises(WorkbenchRagEvalQuestionGenerationError):
        await generator.generate_questions_for_entry(
            claim="Claim",
            possible_questions=(),
            exclusion_scope=None,
            evidence_block=None,
            triples=(),
        )


@pytest.mark.asyncio
async def test_question_generator_rejects_non_json() -> None:
    generator = WorkbenchRagEvalQuestionGenerator(
        llm_dispatch_executor=FakeLlmDispatchExecutor(raw_text="not json"),
        prompt_template="prompt",
    )

    with pytest.raises(WorkbenchRagEvalQuestionGenerationError):
        await generator.generate_questions_for_entry(
            claim="Claim",
            possible_questions=(),
            exclusion_scope=None,
            evidence_block=None,
            triples=(),
        )


def test_question_generator_source_has_no_direct_provider_client_imports() -> None:
    import pathlib

    source = pathlib.Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/llm/"
        "workbench_rag_eval_question_generator.py"
    ).read_text(encoding="utf-8")

    assert "GroqDispatchExecutor" not in source
    assert "OpenAI" not in source
    assert "openai" not in source
    assert "answer_text" not in source
