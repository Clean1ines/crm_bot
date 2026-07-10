from __future__ import annotations

from src.interfaces.composition.workbench_rag_eval import (
    make_workbench_rag_eval_workflow_runtime,
    make_start_workbench_rag_eval_v2,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_dispatch_executor import (
    GroqDispatchExecutor,
)


def test_make_start_workbench_rag_eval_v2_does_not_require_llm_executor() -> None:
    composition = make_start_workbench_rag_eval_v2(pool=object())

    assert composition.pool is not None


def test_workflow_runtime_factory_wires_generic_runtime_and_four_groq_accounts() -> (
    None
):
    settings = LlmRuntimeSettings(
        groq_api_key="test-key-1",
        groq_api_key2="test-key-2",
        groq_api_key3="test-key-3",
        groq_api_key4="test-key-4",
    )

    composition = make_workbench_rag_eval_workflow_runtime(
        pool=object(),
        llm_runtime_settings=settings,
    )

    assert isinstance(composition.llm_executor, GroqDispatchExecutor)
    expected_refs = (
        "groq_org_primary",
        "groq_org_secondary",
        "groq_org_tertiary",
        "groq_org_quaternary",
    )
    assert tuple(composition.llm_executor.transports_by_account_ref) == expected_refs
    assert (
        len(
            {
                id(transport)
                for transport in composition.llm_executor.transports_by_account_ref.values()
            }
        )
        == 4
    )
    assert composition.prepare_llm_dispatch_batch.provider_account_refs == expected_refs
    registry = (
        composition.prepare_llm_dispatch_batch.dispatch_preparation_builder_registry
    )
    assert registry.builder_for(WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND)


def test_workflow_runtime_factory_reuses_generic_prepare_and_execute_boundaries() -> (
    None
):
    composition = make_workbench_rag_eval_workflow_runtime(
        pool=object(),
        llm_runtime_settings=LlmRuntimeSettings(groq_api_key="test-key"),
    )

    assert (
        type(composition.prepare_llm_dispatch_batch).__name__
        == "PrepareLlmDispatchBatch"
    )
    assert (
        type(composition.execute_prepared_llm_dispatch_attempt).__name__
        == "TransactionalExecutePreparedLlmDispatchAttempt"
    )
