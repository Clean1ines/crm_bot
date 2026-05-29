from __future__ import annotations

from pathlib import Path


INGESTION_SERVICE = Path("src/application/services/knowledge_ingestion_service.py")


def test_knowledge_ingestion_service_has_no_asyncpg_dependency() -> None:
    source = INGESTION_SERVICE.read_text(encoding="utf-8")

    assert "import asyncpg" not in source
    assert "from asyncpg" not in source
    assert "asyncpg." not in source
    assert "ForeignKeyViolationError" not in source


def test_knowledge_ingestion_uses_application_deleted_during_processing_error() -> None:
    source = INGESTION_SERVICE.read_text(encoding="utf-8")

    assert "KnowledgeDocumentDeletedDuringProcessingError" in source
    assert "except KnowledgeDocumentDeletedDuringProcessingError" in source
