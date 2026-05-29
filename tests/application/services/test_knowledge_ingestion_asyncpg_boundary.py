from __future__ import annotations

from pathlib import Path


INGESTION_SERVICE = Path("src/application/services/knowledge_ingestion_service.py")


def test_knowledge_ingestion_service_has_no_asyncpg_dependency() -> None:
    source = INGESTION_SERVICE.read_text(encoding="utf-8")

    assert "import asyncpg" not in source
    assert "from asyncpg" not in source
    assert "asyncpg." not in source
    assert "ForeignKeyViolationError" not in source


def test_structured_ingestion_uses_application_deleted_during_processing_error() -> (
    None
):
    ingestion_source = INGESTION_SERVICE.read_text(encoding="utf-8")
    structured_source = Path(
        "src/application/services/knowledge_structured_ingestion_service.py"
    ).read_text(encoding="utf-8")

    assert "KnowledgeDocumentDeletedDuringProcessingError" not in ingestion_source
    assert "KnowledgeDocumentDeletedDuringProcessingError" in structured_source
    assert "except KnowledgeDocumentDeletedDuringProcessingError" in structured_source
