from __future__ import annotations

from dataclasses import dataclass

from src.interfaces.composition.workbench_rag_eval import make_run_workbench_rag_eval
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
)


@dataclass(slots=True)
class FakeLlmDispatchExecutor:
    async def execute_dispatch(
        self,
        execution_input: LlmDispatchExecutionInput,
    ) -> LlmDispatchExecutionResult:
        raise AssertionError("composition test must not execute LLM")


def test_make_run_workbench_rag_eval_composes_use_case(monkeypatch) -> None:
    class FakeEmbeddingSettings:
        provider = "disabled"
        local_model = "test-model"
        vector_dimensions = 384
        local_threads = 1
        executor_max_workers = 1

    monkeypatch.setattr(
        "src.interfaces.composition.workbench_rag_eval.load_embedding_runtime_settings",
        lambda: FakeEmbeddingSettings(),
    )

    use_case = make_run_workbench_rag_eval(
        pool=object(),
        llm_dispatch_executor=FakeLlmDispatchExecutor(),
    )

    assert use_case.question_generation_prompt_version
    assert use_case.question_generation_model
    assert use_case.default_top_k == 5
