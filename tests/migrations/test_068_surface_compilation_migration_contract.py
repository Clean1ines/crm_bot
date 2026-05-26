from pathlib import Path


MIGRATION_PATH = Path("migrations/068_create_knowledge_surface_compilation_tables.sql")


def test_surface_compilation_migration_contains_required_tables_and_indexes() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    required_tables = (
        "knowledge_surface_compiler_runs",
        "knowledge_surface_compiler_stages",
        "knowledge_surface_source_units",
        "knowledge_surfaces",
        "knowledge_surface_relations",
        "knowledge_surface_question_ownership",
        "knowledge_surface_question_reassignments",
        "knowledge_surface_merge_decisions",
    )
    for table in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    required_index_fragments = (
        "idx_surface_runs_project_id",
        "idx_surface_runs_document_id",
        "idx_surface_stages_run_id",
        "idx_surfaces_local_surface_key",
        "idx_surfaces_surface_kind",
        "idx_surfaces_status",
        "idx_surfaces_publication_status",
        "idx_surface_relations_parent_surface_key",
        "idx_surface_relations_child_surface_key",
        "idx_surface_ownership_owner_surface_key",
    )
    for index_fragment in required_index_fragments:
        assert index_fragment in sql
