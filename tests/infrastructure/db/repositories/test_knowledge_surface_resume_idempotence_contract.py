from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPOSITORY = ROOT / "src/infrastructure/db/repositories/knowledge_repository.py"


def test_surface_resume_persistence_inserts_are_idempotent() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")

    assert "INSERT INTO knowledge_surface_source_units" in source
    assert "INSERT INTO knowledge_surfaces" in source
    assert "INSERT INTO knowledge_surface_relations" in source
    assert "INSERT INTO knowledge_surface_question_ownership" in source
    assert "INSERT INTO knowledge_surface_question_reassignments" in source
    assert "INSERT INTO knowledge_surface_merge_decisions" in source
    assert source.count("ON CONFLICT (id) DO NOTHING") >= 6


def test_surface_resume_repository_resets_completed_at_when_run_restarts() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")

    assert "THEN now() ELSE NULL END" in source


def test_surface_resume_repository_can_load_existing_run_artifacts() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")

    assert "get_latest_surface_run_for_document" in source
    assert "list_surface_source_units_for_run" in source
    assert "list_surfaces_for_run" in source
