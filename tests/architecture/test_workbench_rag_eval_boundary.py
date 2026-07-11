from __future__ import annotations

from pathlib import Path


def test_workbench_rag_eval_boundary_avoids_legacy_surfaces_and_answer_text() -> None:
    root = Path("src/contexts/knowledge_workbench/rag_eval")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = (
        "answer_text",
        "knowledge_" + "retrieval_" + "surface",
        "knowledge_workbench_surfaces",
        "FAQSurface",
        "surface",
    )
    for marker in forbidden:
        assert marker not in sources


def test_workbench_rag_eval_retrieval_phase_uses_published_runtime_search() -> None:
    handler_source = Path(
        "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
        "handle_run_workbench_rag_eval_retrieval_evaluation_command.py"
    ).read_text(encoding="utf-8")
    dispatcher_source = Path(
        "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
        "dispatch_workbench_rag_eval_workflow_command.py"
    ).read_text(encoding="utf-8")
    composition_source = Path(
        "src/interfaces/composition/workbench_rag_eval_workflow_runtime.py"
    ).read_text(encoding="utf-8")

    assert "RUN_RETRIEVAL_EVALUATION" in dispatcher_source
    assert (
        "HandleRunWorkbenchRagEvalRetrievalEvaluationCommandHandler"
        in dispatcher_source
    )
    assert "SearchPublishedWorkbenchRuntime" in composition_source
    assert "save_retrieval_results" in handler_source
    assert "save_retrieval_outcomes" in handler_source
    assert "SCHEDULE_ADJUDICATION_WORK" in handler_source
    assert "save_promoted_question_candidates" not in handler_source
    assert (
        "question_generation_batch_executor.generate_for_entries" not in handler_source
    )
    assert "asyncio.gather" not in handler_source
    assert "asyncio.Semaphore" not in handler_source


def test_legacy_rag_eval_router_file_is_deleted() -> None:
    assert not Path("src/interfaces/http/rag_eval.py").exists()


def test_workbench_rag_eval_runtime_does_not_execute_llm_directly() -> None:
    root = Path("src/contexts/knowledge_workbench/rag_eval")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = (
        "LlmDispatchExecutorPort",
        "execute_dispatch",
        "GroqDispatchExecutor",
        "asyncio.Semaphore",
        "asyncio.gather",
    )
    for marker in forbidden:
        assert marker not in sources

    execute_handler = Path(
        "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
        "handle_execute_workbench_rag_eval_question_generation.py"
    ).read_text(encoding="utf-8")
    assert "ExecutePreparedLlmDispatchAttemptCommand" in execute_handler


def test_workbench_rag_eval_apply_does_not_mutate_draft_or_legacy_tables() -> None:
    root = Path("src/contexts/knowledge_workbench/rag_eval")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = (
        "draft_claim_curation_items",
        "editable_payload",
        "original_payload",
        "preview_payload",
        "answer_text",
        "knowledge_" + "retrieval_" + "surface",
        "knowledge_workbench_surfaces",
    )
    for marker in forbidden:
        assert marker not in sources


def test_workbench_rag_eval_capacity_routing_is_outside_generator() -> None:
    generator_source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/llm/"
        "workbench_rag_eval_question_generator.py"
    ).read_text(encoding="utf-8")
    policy_source = Path(
        "src/contexts/knowledge_workbench/rag_eval/application/policies/"
        "workbench_rag_eval_question_generation_route_policy.py"
    ).read_text(encoding="utf-8")

    assert "route_candidate" not in generator_source
    assert "openai/gpt-oss-120b" not in generator_source
    assert "llama-3.1-8b-instant" not in generator_source
    assert "GroqDispatchExecutor" not in generator_source

    assert "qwen/qwen3-32b" in policy_source
    assert "openai/gpt-oss-120b" in policy_source
    assert "WORKBENCH_RAG_EVAL_FORBIDDEN_AUTOMATIC_MODEL_REFS" in policy_source
    assert "llama-3.1-8b-instant" in policy_source
