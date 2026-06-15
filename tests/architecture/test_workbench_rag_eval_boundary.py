from __future__ import annotations

from pathlib import Path


def test_workbench_rag_eval_boundary_avoids_legacy_surfaces_and_answer_text() -> None:
    root = Path("src/contexts/knowledge_workbench/rag_eval")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = (
        "answer_text",
        "knowledge_retrieval_surface",
        "knowledge_workbench_surfaces",
        "FAQSurface",
        "surface",
        "src.application.rag_eval",
        "RagEvalRunner",
    )
    for marker in forbidden:
        assert marker not in sources


def test_workbench_rag_eval_retrieval_phase_uses_published_runtime_search() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/application/use_cases/"
        "run_workbench_rag_eval.py"
    ).read_text(encoding="utf-8")

    assert "SearchPublishedWorkbenchRuntime" in source
    assert "search_published_workbench_runtime.execute" in source
    assert "question_generation_batch_executor.generate_for_entries" in source
    assert "answer" not in source


def test_workbench_rag_eval_http_does_not_reconnect_legacy_rag_eval_router() -> None:
    source = Path("src/interfaces/http/rag_eval.py").read_text(encoding="utf-8")
    knowledge = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "HTTP_410_GONE" in source
    assert "/rag-eval/workbench/run" in knowledge


def test_workbench_rag_eval_question_generator_uses_llm_dispatch_boundary_only() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/llm/"
        "workbench_rag_eval_question_generator.py"
    ).read_text(encoding="utf-8")

    assert "LlmDispatchExecutorPort" in source
    assert "execute_dispatch" in source
    assert "GroqDispatchExecutor" not in source
    assert "OpenAI" not in source
    assert "openai" not in source
    assert "answer_text" not in source


def test_workbench_rag_eval_apply_does_not_mutate_draft_or_legacy_tables() -> None:
    root = Path("src/contexts/knowledge_workbench/rag_eval")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = (
        "draft_claim_curation_items",
        "editable_payload",
        "original_payload",
        "preview_payload",
        "answer_text",
        "knowledge_retrieval_surface",
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

    assert "route_candidate" in generator_source
    assert "openai/gpt-oss-120b" not in generator_source
    assert "llama-3.1-8b-instant" not in generator_source
    assert "GroqDispatchExecutor" not in generator_source

    assert "qwen/qwen3-32b" in policy_source
    assert "openai/gpt-oss-120b" in policy_source
    assert "WORKBENCH_RAG_EVAL_FORBIDDEN_AUTOMATIC_MODEL_REFS" in policy_source
    assert "llama-3.1-8b-instant" in policy_source
