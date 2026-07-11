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


def test_workbench_rag_eval_adjudication_uses_generic_runtime_chain() -> None:
    adjudication_files = [
        Path(
            "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
            "handle_schedule_workbench_rag_eval_adjudication_work_command.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
            "handle_prepare_workbench_rag_eval_adjudication_dispatch_batch.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
            "handle_execute_workbench_rag_eval_adjudication.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
            "handle_execute_workbench_rag_eval_adjudication_command.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
            "handle_reconcile_workbench_rag_eval_adjudication_progress_command.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
            "workbench_rag_eval_dispatch_preparation.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/rag_eval/application/policies/"
            "workbench_rag_eval_adjudication_policy.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/rag_eval/application/policies/"
            "workbench_rag_eval_adjudication_output_validation_policy.py"
        ),
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in adjudication_files
    )
    dispatcher_source = Path(
        "src/contexts/knowledge_workbench/rag_eval/application/workflows/"
        "dispatch_workbench_rag_eval_workflow_command.py"
    ).read_text(encoding="utf-8")
    composition_source = Path(
        "src/interfaces/composition/workbench_rag_eval_workflow_runtime.py"
    ).read_text(encoding="utf-8")

    required = (
        "workbench_rag_eval.adjudication",
        "RagEvalAdjudicationDispatchPreparationBuilder",
        "ExecutePreparedLlmDispatchAttempt",
        "record_observation",
        "RECONCILE_ADJUDICATION_PROGRESS",
        "VALID_TARGET_QUERY",
        "create_promotion_candidates_from_adjudications",
    )
    for marker in required:
        assert (
            marker in combined
            or marker in dispatcher_source
            or marker in composition_source
        )

    assert "WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND: (" in composition_source
    assert "make_adjudication_dispatch_preparation_builder()" in composition_source
    assert (
        "adjudication_executor=ExecuteWorkbenchRagEvalAdjudication"
        in composition_source
    )
    assert "SCHEDULE_ADJUDICATION_WORK" in dispatcher_source
    assert "PREPARE_ADJUDICATION_DISPATCH_BATCH" in dispatcher_source
    assert "EXECUTE_ADJUDICATION" in dispatcher_source
    assert "RECONCILE_ADJUDICATION_PROGRESS" in dispatcher_source

    forbidden = (
        "LlmDispatchExecutorPort.execute_dispatch",
        "execute_dispatch(",
        "GroqDispatchExecutor",
        "Groq client",
        "asyncio.gather",
        "asyncio.Semaphore",
        "manual capacity registry",
        "apply_promotion_candidate(",
        "apply_promotion_candidates_for_target(",
    )
    for marker in forbidden:
        assert marker not in combined
