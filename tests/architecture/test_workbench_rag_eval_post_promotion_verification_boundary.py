from __future__ import annotations

from pathlib import Path


ROOT = Path("src/contexts/knowledge_workbench/rag_eval")
MIGRATION = Path(
    "migrations/129_create_workbench_rag_eval_post_promotion_verifications.sql"
)
MODELS = ROOT / "application/models/workbench_rag_eval_verification.py"
POLICY = (
    ROOT / "application/policies/workbench_rag_eval_promotion_verification_policy.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_post_promotion_verification_migration_persists_plan_metrics_and_outcomes() -> (
    None
):
    migration = _read(MIGRATION)

    assert "knowledge_workbench_rag_eval_verifications" in migration
    assert "knowledge_workbench_rag_eval_verification_queries" in migration
    assert "knowledge_workbench_rag_eval_verification_outcomes" in migration
    assert "UNIQUE (revision_id)" in migration
    assert "policy_version TEXT NOT NULL" in migration
    assert "failure_reasons JSONB NOT NULL" in migration
    assert "metrics JSONB NULL" in migration

    for role in ("'promoted'", "'holdout'", "'baseline'", "'neighbour'"):
        assert role in migration

    for status in (
        "'pending'",
        "'running'",
        "'passed'",
        "'regression_failed'",
        "'failed'",
    ):
        assert status in migration

    assert "'verification_before'" not in migration
    assert "'verification_after'" not in migration
    assert "before_expected_rank" in migration
    assert "after_expected_rank" in migration
    assert "before_classification" in migration
    assert "after_classification" in migration
    assert "UNIQUE (verification_query_id)" in migration


def test_verification_domain_uses_structured_failure_reasons_and_named_policy() -> None:
    models = _read(MODELS)
    policy = _read(POLICY)

    assert "WorkbenchRagEvalVerificationFailureReason" in models
    assert "WorkbenchRagEvalVerificationMetrics" in models
    assert "WorkbenchRagEvalVerificationOutcomePair" in models
    assert "WorkbenchRagEvalPromotionVerificationPolicy" in policy
    assert "WorkbenchRagEvalPromotionVerificationPolicyConfig" in policy
    assert "minimum_promoted_top3_improvement_count" in policy
    assert "maximum_neighbor_top1_regression_count" in policy
    assert "magic" not in policy.lower()


def test_verification_code_does_not_call_embedding_provider_or_mutate_runtime_directly() -> (
    None
):
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            MODELS,
            POLICY,
        )
    )

    assert "EmbeddingGenerationRequest" not in combined
    assert "make_embedding_generation_port" not in combined
    assert "UPDATE knowledge_workbench_runtime_retrieval_entries" not in combined
    assert "asyncio.gather" not in combined
    assert "Semaphore" not in combined
