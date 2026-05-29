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


def test_faq_surface_ingestion_does_not_delete_chunks_on_resume() -> None:
    source = INGESTION.read_text(encoding="utf-8")

    assert (
        "if resume_run is None:\n            await repo.delete_document_chunks(document_id)"
        in source
    )


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
