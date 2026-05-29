from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INGESTION = ROOT / "src/application/services/knowledge_surface_ingestion_service.py"


def test_faq_surface_ingestion_reuses_run_id_through_lifecycle_policy() -> None:
    source = INGESTION.read_text(encoding="utf-8")

    assert "get_latest_surface_run_for_document" in source
    assert "resume_run =" in source
    assert "_should_reuse_surface_run(" in source
    assert "lifecycle_trigger=lifecycle_trigger" in source
    assert "resume_run_id=resume_run_id" in source
    assert "lifecycle_decision=lifecycle_decision" in source
    assert 'latest_run.status in {"running", "failed", "cancelled"}' not in source
    assert (
        "run_id = resume_run.id if resume_run is not None else str(uuid.uuid4())"
        in source
    )


def test_faq_surface_ingestion_cleans_up_only_when_no_resume_run_exists() -> None:
    source = INGESTION.read_text(encoding="utf-8")
    run_id_start = source.index("run_id = resume_run.id if resume_run is not None")
    cleanup_start = source.index(
        "if resume_run is None:", source.index("if not source_units:")
    )
    cleanup_end = source.index("started_at = datetime.now(timezone.utc)", cleanup_start)
    validation_slice = source[run_id_start:cleanup_start]
    cleanup_slice = source[cleanup_start:cleanup_end]

    assert "indexable_chunks = _indexable_chunks(chunks)" in validation_slice
    assert "source_units = _source_units_from_chunks(" in validation_slice
    assert "await repo.cleanup_document_artifacts(" not in validation_slice

    assert "if resume_run is None:" in cleanup_slice
    assert "await repo.cleanup_document_artifacts(" in cleanup_slice
    assert "build_document_reset_cleanup_plan(" in cleanup_slice
    assert "await repo.delete_document_chunks(document_id)" not in source


def test_faq_surface_ingestion_reuses_existing_source_units_and_surfaces() -> None:
    source = INGESTION.read_text(encoding="utf-8")

    assert "list_surface_source_units_for_run" in source
    assert "source_units = existing_source_units" in source
    assert "list_surfaces_for_run" in source
    assert (
        "persisted_surface_ids: set[str] = {surface.id for surface in existing_surfaces}"
        in source
    )


def test_faq_surface_ingestion_passes_source_unit_checkpoints_to_compiler() -> None:
    source = INGESTION.read_text(encoding="utf-8")

    assert "KnowledgeSurfaceCheckpointAwareCompilerPort" in source
    assert "list_surface_stages_for_run" in source
    assert "existing_unit_checkpoints" in source
    assert "set_source_unit_result_checkpoints(existing_unit_checkpoints)" in source
