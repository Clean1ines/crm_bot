from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Mapping
import json

import pytest

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_generation_route_policy import (
    WorkbenchRagEvalQuestionGenerationRoutePolicy,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)


@dataclass(slots=True)
class FakeLlmDispatchExecutor:
    raw_text: str
    status: LlmDispatchExecutionStatus = LlmDispatchExecutionStatus.SUCCEEDED
    last_input: LlmDispatchExecutionInput | None = None

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


def _route(entry_index: int = 0):
    return WorkbenchRagEvalQuestionGenerationRoutePolicy.default().candidate_chain(
        entry_index=entry_index,
        allow_degraded_llama_instant=False,
    )[0]


@pytest.mark.asyncio
async def test_question_generator_uses_supplied_route_candidate_and_metadata() -> None:
    executor = FakeLlmDispatchExecutor(
        raw_text=json.dumps(
            {
                "questions": [
                    {
                        "question": "Как спросит пользователь?",
                        "question_kind": "paraphrase",
                    }
                ]
            },
            ensure_ascii=False,
        )
    )
    route = _route(entry_index=1)
    generator = WorkbenchRagEvalQuestionGenerator.from_prompt_file(
        llm_dispatch_executor=executor,
    )

    result = await generator.generate_questions_for_entry(
        claim="Claim text",
        possible_questions=("Existing?",),
        exclusion_scope="Not X",
        evidence_block="Evidence",
        triples=(),
        route_candidate=route,
    )

    assert result[0].generation_model == "qwen/qwen3-32b"
    assert result[0].generation_account_ref == "groq_org_secondary"
    assert result[0].generation_slot_index == 1
    assert executor.last_input is not None
    allocation = executor.last_input.dispatch_payload["llm_allocation"]
    assert isinstance(allocation, Mapping)
    assert allocation["account_ref"] == "groq_org_secondary"
    assert allocation["slot_index"] == 1


@pytest.mark.asyncio
async def test_question_generator_failed_route_raises_generation_error() -> None:
    generator = WorkbenchRagEvalQuestionGenerator.from_prompt_file(
        llm_dispatch_executor=FakeLlmDispatchExecutor(
            raw_text="{}",
            status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
        ),
    )

    with pytest.raises(WorkbenchRagEvalQuestionGenerationError):
        await generator.generate_questions_for_entry(
            claim="Claim",
            possible_questions=(),
            exclusion_scope=None,
            evidence_block=None,
            triples=(),
            route_candidate=_route(),
        )


def test_question_generator_source_has_no_fallback_or_direct_provider_client() -> None:
    from pathlib import Path

    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/llm/"
        "workbench_rag_eval_question_generator.py"
    ).read_text(encoding="utf-8")

    assert "GroqDispatchExecutor" not in source
    assert "openai/gpt-oss-120b" not in source
    assert "llama-3.1-8b-instant" not in source
    assert "answer_text" not in source
