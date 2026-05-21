from __future__ import annotations

import inspect
from pathlib import Path

from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository


def _method_source(method_name: str, next_method_name: str) -> str:
    source = inspect.getsource(KnowledgeRepository)
    start = source.index(f"async def {method_name}(")
    end = source.index(f"async def {next_method_name}(", start)
    return source[start:end]


def test_document_queries_module_owns_document_read_sql_and_mapping() -> None:
    helper_source = Path(
        "src/infrastructure/db/repositories/knowledge_document_queries.py"
    ).read_text(encoding="utf-8")

    assert "FROM knowledge_documents AS d" in helper_source
    assert "FROM knowledge_documents" in helper_source
    assert "LEFT JOIN knowledge_entries AS ke" in helper_source
    assert "LEFT JOIN knowledge_retrieval_surface AS rs" in helper_source
    assert "FROM model_usage_events" in helper_source
    assert "KnowledgeDocumentView(" in helper_source
    assert "KnowledgeDocumentDetailView(" in helper_source
    assert "normalize_timestamp" in helper_source
    assert "async def is_document_processing_cancelled(" in helper_source
    assert "SELECT status, preprocessing_status" in helper_source


def test_repository_delegates_document_read_sql() -> None:
    repository_source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    get_documents_source = _method_source("get_documents", "get_document")
    get_document_source = _method_source(
        "get_document", "list_document_compiler_batches"
    )
    is_cancelled_source = _method_source(
        "is_document_processing_cancelled", "list_runtime_entry_titles"
    )

    assert "await list_project_documents(" in get_documents_source
    assert "await query_document_detail(" in get_document_source
    assert "await query_document_processing_cancelled(" in is_cancelled_source

    for forbidden in (
        "FROM knowledge_documents AS d",
        "FROM knowledge_documents",
        "LEFT JOIN knowledge_entries AS ke",
        "LEFT JOIN knowledge_retrieval_surface AS rs",
        "FROM model_usage_events",
        "KnowledgeDocumentView(",
        "KnowledgeDocumentDetailView(",
    ):
        assert forbidden not in get_documents_source
        assert forbidden not in get_document_source

    assert "SELECT status, preprocessing_status" not in is_cancelled_source
    assert "FROM knowledge_documents" not in is_cancelled_source

    # Other document curation/delete SQL still belongs to later slices.
    assert "FROM knowledge_documents" in repository_source
    assert "DELETE FROM knowledge_documents" in repository_source
