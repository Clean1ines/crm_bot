from __future__ import annotations

from pathlib import Path


MIGRATION = Path(
    "migrations/117_extend_runtime_retrieval_entries_for_canonical_publish.sql"
)


def test_runtime_retrieval_entry_canonical_publish_columns_are_added() -> None:
    sql = _normalized_migration_sql()

    expected_fragments = (
        "add column if not exists publication_id text null",
        "add column if not exists workflow_run_id text not null default ''",
        "add column if not exists source_document_ref text not null default ''",
        "add column if not exists curation_item_ref text not null default ''",
        (
            "add column if not exists claim_kind text not null "
            "default 'faq_workbench_fact'"
        ),
        "add column if not exists granularity text not null default ''",
        "add column if not exists exclusion_scope text not null default ''",
        "add column if not exists evidence_block text not null default ''",
        "add column if not exists triples jsonb not null default '[]'::jsonb",
        "add column if not exists source_claim_refs jsonb not null default '[]'::jsonb",
        "add column if not exists updated_at timestamptz null",
    )

    for fragment in expected_fragments:
        assert fragment in sql


def test_runtime_retrieval_entry_fact_id_is_transition_nullable_without_fk() -> None:
    sql = _normalized_migration_sql()

    assert "alter column fact_id drop not null" in sql
    assert (
        "drop constraint if exists "
        "knowledge_workbench_runtime_retrieval_entries_fact_id_fkey"
    ) in sql


def _normalized_migration_sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
