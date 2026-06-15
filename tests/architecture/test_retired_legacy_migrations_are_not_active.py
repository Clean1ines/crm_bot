from pathlib import Path


RETIRED_LEGACY_MIGRATIONS = {
    "054_add_knowledge_chunk_embedding_text.sql",
    "055_create_rag_eval.sql",
    "056_replace_knowledge_entry_type_with_entry_kind.sql",
    "058_create_knowledge_source_chunks.sql",
    "059_create_knowledge_entries_and_retrieval_surface.sql",
    "061_rag_eval_entry_evidence_and_failure_actions.sql",
    "062_kcd_stage_h_knowledge_edit_actions.sql",
    "063_rag_eval_review_console.sql",
    "064_rag_eval_review_groups.sql",
    "065_knowledge_curation_console.sql",
    "067_knowledge_edit_actions_allow_in_progress_status.sql",
    "099_drop_artifact_runtime_tables.sql",
}


def test_retired_legacy_migrations_are_not_in_active_root() -> None:
    root = Path("migrations")
    active_sql = {path.name for path in root.glob("*.sql")}
    retired_sql = {path.name for path in (root / "_retired_legacy").glob("*.sql")}

    assert not (active_sql & RETIRED_LEGACY_MIGRATIONS)
    assert RETIRED_LEGACY_MIGRATIONS <= retired_sql


def test_mixed_migration_originals_are_retired_but_active_replacements_remain() -> None:
    root = Path("migrations")
    mixed = {
        "035_create_knowledge_documents.sql",
        "036_knowledge_preprocessing_mvp.sql",
        "050_optimize_knowledge_query_paths.sql",
    }

    active_sql = {path.name for path in root.glob("*.sql")}
    retired_sql = {path.name for path in (root / "_retired_legacy").glob("*.sql")}

    assert mixed <= active_sql
    assert mixed <= retired_sql


def test_runner_does_not_recurse_into_retired_legacy() -> None:
    source = Path("migrations/run_all.py").read_text(encoding="utf-8")

    assert 'glob("*.sql")' in source
    assert 'rglob("*.sql")' not in source


def test_active_migrations_do_not_create_retired_legacy_tables() -> None:
    cleanup = Path("migrations/112_drop_retired_legacy_knowledge_schema.sql")
    forbidden_create_tokens = (
        "CREATE TABLE IF NOT EXISTS knowledge_retrieval_surface",
        "CREATE TABLE knowledge_retrieval_surface",
        "CREATE TABLE IF NOT EXISTS knowledge_entries",
        "CREATE TABLE knowledge_entries",
        "CREATE TABLE IF NOT EXISTS knowledge_source_chunks",
        "CREATE TABLE knowledge_source_chunks",
        "CREATE TABLE IF NOT EXISTS knowledge_edit_actions",
        "CREATE TABLE knowledge_edit_actions",
        "CREATE TABLE IF NOT EXISTS rag_eval_datasets",
        "CREATE TABLE rag_eval_datasets",
        "CREATE TABLE IF NOT EXISTS rag_eval_questions",
        "CREATE TABLE rag_eval_questions",
        "CREATE TABLE IF NOT EXISTS rag_eval_results",
        "CREATE TABLE rag_eval_results",
        "CREATE TABLE IF NOT EXISTS rag_eval_review_groups",
        "CREATE TABLE rag_eval_review_groups",
        "CREATE TABLE IF NOT EXISTS rag_eval_jobs",
        "CREATE TABLE rag_eval_jobs",
        "CREATE TABLE IF NOT EXISTS pipeline_artifacts",
        "CREATE TABLE pipeline_artifacts",
        "CREATE TABLE IF NOT EXISTS knowledge_workbench_surfaces",
        "CREATE TABLE knowledge_workbench_surfaces",
        "CREATE TABLE IF NOT EXISTS knowledge_workbench_surface_cards",
        "CREATE TABLE knowledge_workbench_surface_cards",
    )

    offenders: list[str] = []
    for path in sorted(Path("migrations").glob("*.sql")):
        if path == cleanup:
            continue
        source = path.read_text(encoding="utf-8")
        for token in forbidden_create_tokens:
            if token in source:
                offenders.append(f"{path}: {token}")

    assert offenders == []
