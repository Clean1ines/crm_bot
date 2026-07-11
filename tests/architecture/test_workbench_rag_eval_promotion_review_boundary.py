from pathlib import Path


REVIEW_PATHS = (
    Path(
        "src/contexts/knowledge_workbench/rag_eval/application/use_cases/"
        "approve_workbench_rag_eval_promotion_candidate.py"
    ),
    Path(
        "src/contexts/knowledge_workbench/rag_eval/application/use_cases/"
        "reject_workbench_rag_eval_promotion_candidate.py"
    ),
    Path(
        "src/contexts/knowledge_workbench/rag_eval/application/policies/"
        "workbench_rag_eval_promotion_review_transition_policy.py"
    ),
)

FORBIDDEN = (
    "embedding_generation_port",
    "make_embedding_generation_port",
    "apply_promotion",
    "apply_promotions_batch",
    "runtime_entry",
    "ExecutePreparedLlmDispatchAttempt",
    "GroqDispatchExecutor",
)


def test_promotion_review_path_has_no_application_or_llm_dependencies() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in REVIEW_PATHS)

    for forbidden in FORBIDDEN:
        assert forbidden not in combined
