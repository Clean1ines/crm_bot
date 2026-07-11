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


def test_promotion_application_requires_approved_source_state() -> None:
    repository_source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/postgres/"
        "postgres_workbench_rag_eval_repository.py"
    ).read_text(encoding="utf-8")

    assert (
        repository_source.count(
            "target.status is not WorkbenchRagEvalPromotionStatus.APPROVED"
        )
        == 2
    )

    forbidden_guards = (
        "WorkbenchRagEvalPromotionStatus.CANDIDATE,\n"
        "                        WorkbenchRagEvalPromotionStatus.APPROVED",
        "promotion.status IN ('candidate'",
        "promotion.status IN ('approved', 'applying', 'applied')",
    )
    for forbidden in forbidden_guards:
        assert forbidden not in repository_source

    assert (
        "promotion.run_id = $2 AND promotion.status = 'approved'" in repository_source
    )
