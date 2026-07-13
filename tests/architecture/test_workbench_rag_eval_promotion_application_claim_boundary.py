from __future__ import annotations

from pathlib import Path


ROOT = Path("src/contexts/knowledge_workbench/rag_eval")
SINGLE = ROOT / "application/use_cases/apply_workbench_rag_eval_promotion.py"
BATCH = ROOT / "application/use_cases/apply_workbench_rag_eval_promotions_batch.py"
PORT = ROOT / "application/ports/workbench_rag_eval_repository_port.py"
REPOSITORY = ROOT / "infrastructure/postgres/postgres_workbench_rag_eval_repository.py"
MODEL = ROOT / "application/models/workbench_rag_eval_embedding_revision.py"
POLICY = (
    ROOT / "application/policies/workbench_rag_eval_promotion_application_policy.py"
)
ERRORS = ROOT / "application/errors/workbench_rag_eval_promotion_application_errors.py"
HTTP = Path("src/interfaces/http/knowledge.py")
COMPOSITION = Path("src/interfaces/composition/workbench_rag_eval.py")
MIGRATION = Path("migrations/128_create_workbench_rag_eval_embedding_revisions.sql")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_all_application_consumers_use_persisted_claim_before_provider() -> None:
    single = _read(SINGLE)
    batch = _read(BATCH)
    port = _read(PORT)
    repository = _read(REPOSITORY)
    http = _read(HTTP)
    composition = _read(COMPOSITION)

    assert "grouped_application.execute(" in single
    assert 'mode="selected"' in single
    assert '"all_candidates_for_run"' in batch
    assert "make_apply_workbench_rag_eval_promotions_batch" in http
    assert "make_apply_workbench_rag_eval_promotions_batch(" in composition
    assert "grouped_application=make_apply_workbench_rag_eval_promotions_batch" in (
        composition
    )

    for marker in (
        "claim_promotion_application(",
        "complete_promotion_application_claim(",
        "fail_promotion_application_claim(",
        "persist_promotion_application_revision(",
    ):
        assert marker in batch
        assert marker in port
        assert marker in repository

    claim_index = batch.index("claim_promotion_application(")
    provider_index = batch.index("embedding = await self._embed(built.text)")
    persistence_index = batch.index("persist_promotion_application_revision(")
    completion_index = batch.index("complete_promotion_application_claim(")
    assert claim_index < provider_index < persistence_index < completion_index

    assert "application_key=application_key" in batch
    assert "lease_owner=lease_owner" in batch
    assert "application_key: str" in port
    assert "lease_owner: str" in port
    assert "application_key: str" in repository
    assert "lease_owner: str" in repository


def test_only_claim_owner_can_generate_and_persist_revision() -> None:
    batch = _read(BATCH)
    repository = _read(REPOSITORY)
    migration = _read(MIGRATION)

    assert "ACQUIRED" in batch
    assert "RECOVERED_EXPIRED_LEASE" in batch
    assert "ALREADY_COMPLETED" in batch
    assert "IN_PROGRESS" in batch
    assert "CONFLICTING_ACTIVE_GROUP" in batch
    assert batch.count("embedding = await self._embed(built.text)") == 1

    assert "status = 'PREPARING'" in repository
    assert "lease_owner != lease_owner" in repository
    assert "lease_expires_at > CURRENT_TIMESTAMP AS lease_is_active" in repository
    assert "APPLICATION_LEASE_LOST" in repository
    assert "promotion application claim completion" in repository
    persist_start = repository.index(
        "    async def persist_promotion_application_revision("
    )
    persist_end = repository.index(
        "    async def list_embedding_revisions(",
        persist_start,
    )
    persist_source = repository[persist_start:persist_end]
    assert "SET status = 'COMPLETED'" in persist_source
    assert "revision_id = $3" in persist_source
    assert "lease_owner = $2" in persist_source
    assert "embedding_generation_port" not in repository
    assert "EmbeddingGenerationRequest" not in repository

    assert "knowledge_workbench_rag_eval_promotion_application_claims" in migration
    assert "WHERE status = 'PREPARING'" in migration
    assert "application_key TEXT PRIMARY KEY" in migration
    assert "application_key TEXT NOT NULL UNIQUE" in migration


def test_active_promoted_alias_limit_is_separate_from_baseline_aliases() -> None:
    model = _read(MODEL)
    policy = _read(POLICY)
    repository = _read(REPOSITORY)

    assert "active_promoted_questions: tuple[str, ...]" in model
    assert "snapshot.active_promoted_questions" in policy
    assert "len(existing_by_normalized)" not in policy
    assert "applied.status = 'applied'" in repository
    assert "active_promoted_questions" in repository
    assert "normalize_workbench_rag_eval_question" in repository


def test_embedding_dimensions_are_canonically_fixed_at_384() -> None:
    model = _read(MODEL)
    repository = _read(REPOSITORY)
    composition = _read(COMPOSITION)
    migration = _read(MIGRATION)

    assert "WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS = 384" in model
    assert "value != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS" in model
    assert "dimensions != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS" in repository
    assert "vector violates canonical dimensions" in repository
    assert "settings.vector_dimensions != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS" in (
        composition
    )
    assert "previous_embedding vector(384) NOT NULL" in migration
    assert "new_embedding vector(384) NOT NULL" in migration
    assert "CHECK (embedding_dimensions = 384)" in migration
    assert "CHECK (embedding_dimensions > 0)" not in migration


def test_expected_concurrency_errors_remain_http_conflicts() -> None:
    errors = _read(ERRORS)
    http = _read(HTTP)

    for marker in (
        'APPLICATION_IN_PROGRESS = "application_in_progress"',
        'CONFLICTING_ACTIVE_APPLICATION = "conflicting_active_application"',
        'APPLICATION_LEASE_LOST = "application_lease_lost"',
    ):
        assert marker in errors

    assert "WorkbenchRagEvalPromotionConflictError" in http
    assert "status_code=409" in http
