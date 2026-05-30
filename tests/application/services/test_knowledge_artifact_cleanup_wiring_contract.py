from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INGESTION = ROOT / "src/application/services/knowledge_ingestion_service.py"
SURFACE_INGESTION = (
    ROOT / "src/application/services/knowledge_surface_ingestion_service.py"
)
REPOSITORY = ROOT / "src/infrastructure/db/repositories/knowledge_repository.py"


def _method_slice(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_knowledge_ingestion_process_document_uses_cleanup_contract() -> None:
    facade_source = Path(
        "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")
    structured_source = Path(
        "src/application/services/knowledge_structured_ingestion_service.py"
    ).read_text(encoding="utf-8")

    assert "KnowledgeStructuredIngestionService" in facade_source
    assert "build_document_reset_cleanup_plan" not in facade_source

    assert "build_document_reset_cleanup_plan" in structured_source
    assert "cleanup_document_artifacts(" in structured_source
    assert "KnowledgeDocumentDeletedDuringProcessingError" in structured_source


def test_faq_surface_normal_no_resume_uses_cleanup_contract() -> None:
    source = SURFACE_INGESTION.read_text(encoding="utf-8")

    assert "build_document_reset_cleanup_plan" in source
    assert "async def cleanup_document_artifacts(" in source
    assert "if resume_run is None:" in source
    assert "await repo.cleanup_document_artifacts(" in source
    assert "project_id=project_id" in source
    assert "document_id=document_id" in source
    assert "await repo.delete_document_chunks(document_id)" not in source


def test_faq_surface_resume_paths_preserve_artifacts() -> None:
    source = SURFACE_INGESTION.read_text(encoding="utf-8")
    validation_slice = _method_slice(
        source,
        "resume_run = (",
        "if resume_run is None:",
    )
    cleanup_slice = _method_slice(
        source,
        "if not source_units:",
        "started_at = datetime.now(timezone.utc)",
    )

    assert "indexable_chunks = filter_indexable_chunks(chunks)" in validation_slice
    assert "source_units = _source_units_from_chunks(" in validation_slice
    assert "await repo.cleanup_document_artifacts(" not in validation_slice

    assert "if resume_run is None:" in cleanup_slice
    assert "await repo.cleanup_document_artifacts(" in cleanup_slice
    assert "build_document_reset_cleanup_plan(" in cleanup_slice
    assert "if resume_run is not None:" not in cleanup_slice
    assert "lifecycle_decision.can_auto_resume" in source
    assert "lifecycle_decision.can_manual_resume" in source


def test_repository_delete_and_clear_use_cleanup_plans() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")

    delete_chunks = _method_slice(
        source,
        "async def delete_document_chunks",
        "async def delete_document(",
    )
    delete_document = _method_slice(
        source,
        "async def delete_document(",
        "async def get_document_for_curation",
    )
    clear_project_start = source.index("async def clear_project_knowledge")
    clear_project = source[clear_project_start:]

    assert "Deprecated wrapper" in delete_chunks
    assert "build_document_reset_cleanup_plan(" in delete_chunks
    assert "await self.cleanup_document_artifacts(" in delete_chunks

    assert "build_document_delete_cleanup_plan(" in delete_document
    assert "await self.cleanup_document_artifacts(" in delete_document
    assert "DELETE FROM knowledge_documents WHERE id = $1" not in delete_document
    assert "await self._cancel_document_jobs(" not in delete_document

    assert "build_project_clear_cleanup_plan(" in clear_project
    assert "await self.cleanup_project_artifacts(" in clear_project
    assert "DELETE FROM knowledge_documents WHERE project_id = $1" not in clear_project
    assert "await self._cancel_project_knowledge_jobs(" not in clear_project
