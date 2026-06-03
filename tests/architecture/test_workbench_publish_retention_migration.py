from __future__ import annotations

from pathlib import Path


MIGRATION = Path("migrations/071_workbench_publish_retention_cutover.sql")


def test_publish_retention_migration_detaches_final_registry_from_processing_run() -> (
    None
):
    source = MIGRATION.read_text(encoding="utf-8")

    assert "knowledge_workbench_question_registries" in source
    assert "knowledge_workbench_registry_snapshots" in source
    assert "knowledge_workbench_question_registry_entries" in source
    assert "ALTER COLUMN processing_run_id DROP NOT NULL" in source
    assert "ON DELETE SET NULL" in source
    assert "ON DELETE CASCADE" not in source


def test_publish_retention_migration_adds_retention_state_and_final_snapshot_marker() -> (
    None
):
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS retention_state" in source
    assert "ADD COLUMN IF NOT EXISTS is_final_published" in source
    assert "idx_kwb_snapshots_final_published" in source
    assert "idx_kwb_documents_retention_state" in source
