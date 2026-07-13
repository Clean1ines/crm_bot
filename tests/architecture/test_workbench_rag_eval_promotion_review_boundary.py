from __future__ import annotations

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

REVIEW_FORBIDDEN = (
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

    for forbidden in REVIEW_FORBIDDEN:
        assert forbidden not in combined


ROOT = Path("src/contexts/knowledge_workbench/rag_eval")
SINGLE = ROOT / "application/use_cases/apply_workbench_rag_eval_promotion.py"
BATCH = ROOT / "application/use_cases/apply_workbench_rag_eval_promotions_batch.py"
PORT = ROOT / "application/ports/workbench_rag_eval_repository_port.py"
REPOSITORY = ROOT / "infrastructure/postgres/postgres_workbench_rag_eval_repository.py"
POLICY = (
    ROOT / "application/policies/workbench_rag_eval_promotion_application_policy.py"
)
MODEL = ROOT / "application/models/workbench_rag_eval_embedding_revision.py"
HTTP = Path("src/interfaces/http/knowledge.py")
COMPOSITION = Path("src/interfaces/composition/workbench_rag_eval.py")
MIGRATION = Path("migrations/128_create_workbench_rag_eval_embedding_revisions.sql")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_all_application_consumers_share_grouped_revision_boundary() -> None:
    single = _read(SINGLE)
    batch = _read(BATCH)
    port = _read(PORT)
    repository = _read(REPOSITORY)
    http = _read(HTTP)
    composition = _read(COMPOSITION)

    assert "grouped_application.execute(" in single
    assert "persist_promotion_application_revision(" in batch
    assert "persist_promotion_application_revision(" in port
    assert "persist_promotion_application_revision(" in repository
    assert "make_apply_workbench_rag_eval_promotions_batch(" in composition
    assert "grouped_application=make_apply_workbench_rag_eval_promotions_batch" in (
        composition
    )
    assert 'mode="selected"' in single
    assert '"all_candidates_for_run"' in batch
    assert "make_apply_workbench_rag_eval_promotions_batch" in http


def test_no_production_callable_direct_runtime_mutation_method_remains() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("src").rglob("*.py")
    )
    forbidden = (
        "def apply_promotion_candidate(",
        "def apply_promotion_candidates_for_target(",
        ".apply_promotion_candidate(",
        ".apply_promotion_candidates_for_target(",
    )
    for marker in forbidden:
        assert marker not in combined


def test_approved_is_required_in_policy_service_and_locked_repository() -> None:
    policy = _read(POLICY)
    batch = _read(BATCH)
    repository = _read(REPOSITORY)

    application_start = repository.index(
        "    async def persist_promotion_application_revision("
    )
    application_end = repository.index(
        "    async def list_embedding_revisions(",
        application_start,
    )
    locked_application = repository[application_start:application_end]

    assert "candidate.status is not WorkbenchRagEvalPromotionStatus.APPROVED" in policy
    assert (
        "target.status in {\n"
        "                WorkbenchRagEvalPromotionStatus.APPROVED,\n"
        "                WorkbenchRagEvalPromotionStatus.APPLIED," in batch
    )
    assert (
        "candidate.status is not WorkbenchRagEvalPromotionStatus.APPROVED"
        in locked_application
    )
    assert "WorkbenchRagEvalPromotionStatus.CANDIDATE" not in batch
    assert "status = 'approved'" in locked_application
    assert "status = 'candidate'" not in locked_application


def test_one_grouped_embedding_generation_occurs_per_target_not_per_candidate() -> None:
    batch = _read(BATCH)

    assert "for runtime_entry_id in sorted(grouped):" in batch
    assert batch.count("embedding = await self._embed(built.text)") == 1
    assert "for candidate in decision.applicable_candidates" in batch
    assert batch.index("embedding = await self._embed(built.text)") > batch.index(
        "for runtime_entry_id in sorted(grouped):"
    )
    assert "# one grouped embedding generation" in batch


def test_network_embedding_is_outside_repository_transaction() -> None:
    batch = _read(BATCH)
    repository = _read(REPOSITORY)

    assert "EmbeddingGenerationRequest" in batch
    assert ".transaction()" not in batch
    assert "embedding_generation_port" not in repository
    assert "EmbeddingGenerationRequest" not in repository
    assert "async with connection.transaction():" in repository


def test_revision_model_and_active_guard_are_required_architecture_markers() -> None:
    model = _read(MODEL)
    repository = _read(REPOSITORY)
    migration = _read(MIGRATION)

    assert "class WorkbenchRagEvalEmbeddingRevision" in model
    assert "PENDING_VERIFICATION" in model
    assert "# active revision guard" in repository
    assert "status = 'pending_verification'" in repository
    assert "WHERE status = 'pending_verification'" in migration
    assert "CREATE UNIQUE INDEX" in migration


def test_revision_snapshot_persists_full_previous_and_new_vectors() -> None:
    migration = _read(MIGRATION)

    for column in (
        "previous_embedding_text TEXT NOT NULL",
        "new_embedding_text TEXT NOT NULL",
        "previous_embedding vector(384) NOT NULL",
        "new_embedding vector(384) NOT NULL",
        "previous_promoted_questions JSONB NOT NULL",
        "new_promoted_questions JSONB NOT NULL",
    ):
        assert column in migration
    assert "previous_embedding_hash" not in migration
    assert "new_embedding_hash" not in migration


def test_http_read_projection_does_not_expose_raw_vectors() -> None:
    http = _read(HTTP)
    model = _read(MODEL)

    assert "/embedding-revisions" in http
    read_model = model.split(
        "class WorkbenchRagEvalEmbeddingRevisionReadModel:",
        1,
    )[1].split(
        "class WorkbenchRagEvalPromotionRevisionResult:",
        1,
    )[0]
    assert '"previous_embedding"' not in read_model
    assert '"new_embedding"' not in read_model
